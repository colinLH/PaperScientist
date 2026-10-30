from __future__ import annotations

import asyncio
import hashlib
import re
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from pydantic import Field

from langchain_core.tools import tool

from .memory import text_content
from .agent_profiles import COORDINATION_TOOLS
from .context import agent_status, artifact_refs
from .store import dumps, now


class Scheduler:
    """Isolated resumable children with a bounded pool, mailboxes and durable registry."""

    def __init__(self, service):
        self.service, self.store = service, service.store
        self.tasks = {}
        self.mailboxes = {}
        self.slots = asyncio.Semaphore(service.settings.max_subagents)

    @asynccontextmanager
    async def operation(self, session, tool_name=None):
        """Lease only active child work, never a parent's wait/spawn operation."""
        if not session.get('parent_id') or tool_name in COORDINATION_TOOLS:
            yield
        else:
            async with self.slots:
                yield

    def descendants(self, parent_id):
        result, pending, seen = [], [parent_id], {parent_id}
        while pending:
            for child in self.store.agents(pending.pop()):
                if child['id'] in seen:
                    continue
                seen.add(child['id'])
                result.append(child)
                pending.append(child['id'])
        return result

    def ancestry(self, session):
        depth, root, seen = 0, session['id'], set()
        current = session
        while current.get('parent_id'):
            if current['id'] in seen:
                raise ValueError('Cyclic agent hierarchy')
            seen.add(current['id'])
            depth, root = depth+1, current['parent_id']
            current = self.store.get_session(root)
        return depth, root

    def find(self, parent_id, target):
        agent = next((a for a in self.store.agents(parent_id) if target in {a["id"], a["task_name"]}), None)
        if not agent:
            raise ValueError("Child agent not found under this parent")
        return agent

    def launch(self, parent, settings, agent, message):
        if agent["id"] in self.tasks and not self.tasks[agent["id"]].done():
            raise ValueError("Agent is running; use send_message")
        if agent.get("isolated_review"):
            settings = settings.with_overrides(allow_execution=False, extract_memory=False)
        agent.update(status="queued", updated_at=now(), result="", error="")
        self.store.save_agent(agent)

        async def run():
            try:
                agent.update(status="running", updated_at=now())
                self.store.save_agent(agent)
                await self.service.emit_to(parent["id"], "subagent", agent.copy())
                result = await self.service.run_turn(agent["id"], message, settings=settings,
                    user_id=parent["user_id"], project_id=parent["project_id"],
                    parent_id=parent["id"], role=agent["role"])
                agent.update(status="completed" if result.get("stop_reason", "completed") == "completed" else "interrupted",
                             result=result["content"], artifacts=result.get('artifacts', []),
                             stop_reason=result.get("stop_reason", "completed"), updated_at=now())
            except asyncio.CancelledError:
                await self.cancel_parent(agent['id'])
                agent.update(status="cancelled", error="Cancelled; persisted history can be resumed", updated_at=now())
                raise
            except Exception as exc:
                await self.cancel_parent(agent['id'])
                agent.update(status="error", error=self.service.safe_error(exc), updated_at=now())
            finally:
                self.store.save_agent(agent)
                await self.service.emit_to(parent["id"], "subagent", agent.copy())
        self.tasks[agent["id"]] = asyncio.create_task(run(), name="research-child-"+agent["id"])
        return agent

    async def cancel_parent(self, parent_id):
        tasks = [self.tasks[a["id"]] for a in self.descendants(parent_id)
                 if a["id"] in self.tasks and not self.tasks[a["id"]].done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def shutdown(self):
        tasks = [t for t in self.tasks.values() if not t.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def tools(self, parent, settings, profile=None):
        parent_id = parent["id"]
        profile = profile or self.service.profiles.for_session(self.store, parent)

        @tool
        def list_agent_profiles() -> list:
            """Discover this parent's permitted specialist/leaf profiles and their scoped tools, skills and checks."""
            result = []
            for name in sorted(profile.children):
                child, ceiling = delegation(name)
                metadata = child.metadata()
                metadata.update(tools=ceiling['tools'], skills=ceiling['skills'])
                result.append(metadata)
            return result

        def delegation(role):
            if parent_id not in self.service.tool_capabilities:
                # Public scheduler tools can be used directly, without a prior model binding.
                from .tools import ToolSet
                ToolSet(self.service, parent, settings, self, bool(parent.get('parent_id')))
            names = set(self.service.tool_capabilities.get(parent_id, ()))
            # An orchestrator may pass artifacts into its child even though it has no parent itself.
            if not parent.get('parent_id') and profile.allows_tool('copy_parent_artifact'):
                names.add('copy_parent_artifact')
            return self.service.profiles.delegate(profile, role, names, self.service.catalog)

        @tool
        async def spawn_agent(task_name: Annotated[str, Field(pattern=r"^[a-z0-9_-]{1,40}$", description="Unique lowercase English task name, e.g. experiment-review")],
                              message: str, role: str = "researcher",
                              fork_context: bool = False, isolated_review: bool = False,
                              artifact_ids: list[str] | None = None) -> dict:
            """Delegate a substantial subtask. For blind reviews set role=reviewer, isolated_review=true and explicit source artifact_ids: only a frozen packet is copied, with no inherited memory/project or peer artifacts."""
            if not re.fullmatch(r"[a-z0-9_-]{1,40}", task_name):
                raise ValueError("task_name must use 1–40 lowercase English letters, digits, underscores or hyphens")
            child_profile, capabilities = delegation(role)
            depth, root = self.ancestry(parent)
            if depth >= settings.max_agent_depth:
                raise ValueError('Agent hierarchy depth budget reached')
            agents = self.store.agents(parent_id)
            if any(a["task_name"] == task_name for a in agents):
                raise ValueError("Task name exists; use followup_task to resume")
            if len(self.descendants(root)) >= settings.max_agent_tasks:
                raise ValueError("Research tree agent budget reached; resume an existing child")
            if isolated_review and (child_profile.name != "reviewer" or fork_context):
                raise ValueError("Isolated review requires reviewer role and fork_context=false")
            agent = {"id": "child_"+uuid.uuid4().hex, "parent_id": parent_id, "task_name": task_name,
                     "role": child_profile.name, "capabilities": capabilities,
                     "depth": depth+1, "root_id": root, "created_at": now(), "status": "queued"}
            if isolated_review:
                selected = {a["id"]: a for a in self.store.artifacts(parent_id)}
                if not artifact_ids or any(aid not in selected for aid in artifact_ids):
                    raise ValueError("Provide explicit source artifact IDs from this parent session")
                if len(artifact_ids) > 30 or sum(Path(selected[aid]["path"]).stat().st_size for aid in artifact_ids) > 50_000_000:
                    raise ValueError("Review packet limit: 30 artifacts and 50MB")
                agent.update(isolated_review=True, review_packet=[])
                for aid in dict.fromkeys(artifact_ids):
                    item = selected[aid]
                    path = Path(item["path"])
                    payload = path.read_bytes()
                    digest = hashlib.sha256(payload).hexdigest()
                    if digest != item["metadata"]["sha256"]:
                        raise ValueError("Review source changed after registration")
                    destination = f"review_packet/{aid}_{path.name}"
                    target = self.store.file(agent["id"], destination)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(payload)
                    self.store.artifact(agent["id"], target, "review_source", {"source_artifact":aid})
                    agent["review_packet"].append({"source_artifact":aid,"path":destination,"sha256":digest})
                return self.launch(parent, settings.with_overrides(allow_execution=False, extract_memory=False),
                    agent, "ISOLATED REVIEW: assess only the frozen source packet and this assignment. "
                    "Do not seek other reviewers' reports.\n"+dumps({"assignment":message,"packet":agent["review_packet"]}))
            context = {"project": self.store.project(parent), "assignment": message,
                       "parent_artifacts": [{"id":a["id"],"path":str(Path(a["path"]).relative_to(self.store.workspace(parent_id)))} for a in self.store.artifacts(parent_id)[-20:]]}
            if fork_context:
                context["parent_transcript"] = [{"role":m.type,"text":text_content(m)[:3000]}
                    for _, m in self.store.history(parent_id)[-16:]]
            return self.launch(parent, settings, agent, "Delegated task and context (parent evidence):\n"+dumps(context))

        @tool
        def list_agents() -> list:
            """List bounded child status/result previews. Use read_agent pagination for full evidence."""
            return [agent_status(a) for a in self.store.agents(parent_id)]

        @tool
        async def wait_agent(target: str = "", timeout: int = 30) -> list:
            """Wait up to 60 seconds for a selected child or the first running child to finish. Returns current statuses and completed results."""
            agents = [self.find(parent_id, target)] if target else self.store.agents(parent_id)
            tasks = [self.tasks[a["id"]] for a in agents if a["id"] in self.tasks and not self.tasks[a["id"]].done()]
            if tasks:
                await asyncio.wait(tasks, timeout=max(0, min(timeout, 60)), return_when=asyncio.FIRST_COMPLETED)
            return [agent_status(self.find(parent_id, a["id"])) for a in agents]

        @tool
        def read_agent(target: str, artifact_offset: int = 0, artifact_limit: int = 10,
                       result_offset: int = 0, max_chars: int = 6000, history_limit: int = 4) -> dict:
            """Read paginated child results and artifact references. Follow next offsets for omitted evidence; recent history is a bounded preview."""
            agent = self.find(parent_id, target)
            artifacts = self.store.artifacts(agent["id"])
            start, limit = max(0, artifact_offset), max(1, min(artifact_limit, 40))
            offset, chars = max(0, result_offset), max(200, min(max_chars, 12000))
            result = str(agent.get("result") or "")
            count = max(0, min(history_limit, 8))
            history = self.store.history(agent["id"])[-count:] if count else []
            per_message = max(200, chars // max(1, len(history)))
            return {**agent_status(agent), "result": result[offset:offset+chars],
                    "next_result_offset": offset+chars if offset+chars < len(result) else None,
                    "artifacts": artifact_refs(artifacts[start:start+limit]), "artifact_count": len(artifacts),
                    "next_artifact_offset": start+limit if start+limit < len(artifacts) else None,
                    "recent_history": [{"id":mid,"role":m.type,"content":text_content(m)[:per_message],
                                        "content_chars":len(text_content(m))} for mid,m in history]}

        @tool
        async def followup_task(target: str, message: str) -> dict:
            """Resume a completed, interrupted, errored or cancelled child using its durable history and workspace."""
            agent = self.find(parent_id, target)
            if self.service.profiles.get(agent['role']).name not in profile.children:
                raise PermissionError('This profile no longer permits that child role')
            return agent_status(self.launch(parent, settings, agent, message))

        @tool
        def send_message(target: str, message: str) -> dict:
            """Queue a coordination message for a running child. Idle children should use followup_task."""
            agent = self.find(parent_id, target)
            if agent["status"] not in {"running", "queued"}:
                raise ValueError("Child is idle; use followup_task")
            self.mailboxes.setdefault(agent["id"], []).append(message)
            self.store.event(agent["id"], "parent_message", {"message": message})
            return {"status":"queued", "target":agent["id"]}

        @tool
        async def cancel_agent(target: str) -> dict:
            """Cancel a running child while preserving its transcript and files for follow-up."""
            agent = self.find(parent_id, target)
            await self.cancel_parent(agent['id'])
            task = self.tasks.get(agent["id"])
            if task and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            return self.find(parent_id, agent["id"])

        @tool
        def import_agent_artifact(target: str, artifact_id: str, destination: str) -> dict:
            """Copy a reviewed child's artifact into the parent workspace without overwriting files; preserves provenance."""
            agent = self.find(parent_id, target)
            source = next((a for a in self.store.artifacts(agent["id"]) if a["id"] == artifact_id), None)
            if not source:
                raise ValueError("Artifact not found for that child")
            dest = self.store.file(parent_id, destination)
            if dest.exists():
                raise ValueError("Destination exists")
            source_path = Path(source['path'])
            if not source_path.resolve().is_relative_to(self.store.workspace(agent['id']).resolve()):
                raise ValueError('Child artifact escapes its workspace')
            if hashlib.sha256(source_path.read_bytes()).hexdigest() != source['metadata'].get('sha256'):
                raise ValueError('Child artifact changed after registration; register the current version first')
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source["path"], dest)
            return self.store.artifact(parent_id, dest, source["kind"], {**source["metadata"],
                "source_child":agent["id"], "source_artifact":artifact_id})

        return [list_agent_profiles, spawn_agent, list_agents, wait_agent, read_agent, followup_task, send_message, cancel_agent, import_agent_artifact]
