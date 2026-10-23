from __future__ import annotations

import asyncio
import hashlib
import re
import shutil
import uuid
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from langchain_core.tools import tool

from .memory import text_content
from .prompts import ROLES
from .store import dumps, now


class Scheduler:
    """Isolated resumable children with a bounded pool, mailboxes and durable registry."""

    def __init__(self, service):
        self.service, self.store = service, service.store
        self.tasks = {}
        self.mailboxes = {}
        self.slots = asyncio.Semaphore(service.settings.max_subagents)

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
                async with self.slots:
                    agent.update(status="running", updated_at=now())
                    self.store.save_agent(agent)
                    await self.service.emit_to(parent["id"], "subagent", agent.copy())
                    result = await self.service.run_turn(agent["id"], message, settings=settings,
                        user_id=parent["user_id"], project_id=parent["project_id"],
                        parent_id=parent["id"], role=agent["role"])
                    agent.update(status="completed" if result.get("stop_reason", "completed") == "completed" else "interrupted",
                                 result=result["content"], stop_reason=result.get("stop_reason", "completed"), updated_at=now())
            except asyncio.CancelledError:
                agent.update(status="cancelled", error="Cancelled; persisted history can be resumed", updated_at=now())
                raise
            except Exception as exc:
                agent.update(status="error", error=self.service.safe_error(exc), updated_at=now())
            finally:
                self.store.save_agent(agent)
                await self.service.emit_to(parent["id"], "subagent", agent.copy())
        self.tasks[agent["id"]] = asyncio.create_task(run(), name="research-child-"+agent["id"])
        return agent

    async def cancel_parent(self, parent_id):
        tasks = [self.tasks[a["id"]] for a in self.store.agents(parent_id)
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

    def tools(self, parent, settings):
        parent_id = parent["id"]

        @tool
        async def spawn_agent(task_name: Annotated[str, Field(pattern=r"^[a-z0-9_-]{1,40}$", description="Unique lowercase English task name, e.g. experiment-review")],
                              message: str, role: Literal["researcher", "methodologist", "engineer", "analyst", "writer", "reviewer"] = "researcher",
                              fork_context: bool = False, isolated_review: bool = False,
                              artifact_ids: list[str] | None = None) -> dict:
            """Delegate a substantial subtask. For blind reviews set role=reviewer, isolated_review=true and explicit source artifact_ids: only a frozen packet is copied, with no inherited memory/project or peer artifacts."""
            if not re.fullmatch(r"[a-z0-9_-]{1,40}", task_name) or role not in ROLES:
                raise ValueError("task_name must use 1–40 lowercase English letters, digits, underscores or hyphens; role must be a listed role")
            agents = self.store.agents(parent_id)
            if any(a["task_name"] == task_name for a in agents):
                raise ValueError("Task name exists; use followup_task to resume")
            if sum(a["status"] in {"queued", "running"} for a in agents) >= settings.max_subagents:
                raise ValueError("Subagent concurrency budget reached; wait for an existing child")
            if len(agents) >= 24:
                raise ValueError("Session child-agent budget reached; resume an existing child")
            if isolated_review and (role != "reviewer" or fork_context):
                raise ValueError("Isolated review requires reviewer role and fork_context=false")
            agent = {"id": "child_"+uuid.uuid4().hex, "parent_id": parent_id, "task_name": task_name,
                     "role": role, "created_at": now(), "status": "queued"}
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
            """List this session's children, status, results and IDs after resume or compaction."""
            return self.store.agents(parent_id)

        @tool
        async def wait_agent(target: str = "", timeout: int = 30) -> list:
            """Wait up to 60 seconds for a selected child or the first running child to finish. Returns current statuses and completed results."""
            agents = [self.find(parent_id, target)] if target else self.store.agents(parent_id)
            tasks = [self.tasks[a["id"]] for a in agents if a["id"] in self.tasks and not self.tasks[a["id"]].done()]
            if tasks:
                await asyncio.wait(tasks, timeout=max(0, min(timeout, 60)), return_when=asyncio.FIRST_COMPLETED)
            return [self.find(parent_id, a["id"]) for a in agents]

        @tool
        def read_agent(target: str) -> dict:
            """Inspect a child's result, raw recent evidence and artifact IDs before integrating its work."""
            agent = self.find(parent_id, target)
            return {**agent, "artifacts": self.store.artifacts(agent["id"]),
                    "recent_history": [{"id":mid,"role":m.type,"content":m.content} for mid,m in self.store.history(agent["id"])[-8:]]}

        @tool
        async def followup_task(target: str, message: str) -> dict:
            """Resume a completed, interrupted, errored or cancelled child using its durable history and workspace."""
            return self.launch(parent, settings, self.find(parent_id, target), message)

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
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source["path"], dest)
            return self.store.artifact(parent_id, dest, source["kind"], {**source["metadata"],
                "source_child":agent["id"], "source_artifact":artifact_id})

        return [spawn_agent, list_agents, wait_agent, read_agent, followup_task, send_message, cancel_agent, import_agent_artifact]
