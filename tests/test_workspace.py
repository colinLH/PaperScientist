import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

from paperscientist.api import create_app
from paperscientist.config import Settings
from paperscientist.memory import MemoryManager
from paperscientist.runtime import AgentService
from paperscientist.store import Store, short_title
from paperscientist.workspace import Workspace


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name))
        self.ui = Workspace(self.store)

    def test_named_projects_group_restore_and_filter_sessions(self):
        project = self.store.create_project("Agent 记忆研究")
        self.store.session("s1", project_id=project["id"])
        self.store.append("s1", HumanMessage(content="请帮我设计记忆消融实验"))
        self.store.append("s1", AIMessage(content="建议比较工作记忆与项目记忆。"))
        self.store.session("s2", project_id=project["id"])
        self.store.append("s2", HumanMessage(content="整理相关论文"))
        self.store.session("child", project_id=project["id"], parent_id="s1")
        self.store.session("private", user_id="other", project_id=project["id"])
        groups = self.ui.groups()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["name"], "Agent 记忆研究")
        self.assertEqual({s["id"] for s in groups[0]["sessions"]}, {"s1", "s2"})
        self.assertEqual(self.ui.groups("消融")[0]["sessions"][0]["id"], "s1")
        self.assertEqual(len(self.ui.history("s1")), 2)
        self.assertIn("项目记忆", self.ui.history("s1")[1]["content"])
        reopened = Store(Path(self.temp.name))
        self.assertEqual(reopened.project_list()[0]["name"], "Agent 记忆研究")
        empty = self.store.create_project("空项目")
        self.assertIn(empty["id"], {p["id"] for p in self.store.project_list()})

    def test_downloads_are_immutable_bounded_and_ignore_unregistered_changes(self):
        self.store.session("s1")
        p = self.store.file("s1", "result.txt")
        p.write_text("verified v1")
        self.store.artifact("s1", p, "source")
        old = Path(self.ui.downloads("s1", limit=1)[0])
        p.write_text("partial overwrite")
        self.assertEqual(old.read_text(), "verified v1")
        p.write_text("verified v2")
        self.store.artifact("s1", p, "source")
        new = self.ui.downloads("s1", limit=1)
        self.assertEqual(len(new), 1)
        self.assertNotEqual(Path(new[0]), old)
        self.assertEqual(Path(new[0]).read_text(), "verified v2")

    def test_attachments_are_explicit_and_cannot_cross_sessions(self):
        source = Path(self.temp.name)/"data.csv"
        source.write_text("method,value\nbase,0.5\n")
        paths = self.ui.attach([source], "s1", "default")
        self.assertIn(paths[0], self.ui.message("分析数据", paths, "s1"))
        self.assertEqual(self.ui.message("继续", [], "s1"), "继续")
        self.store.session("s2")
        with self.assertRaises(ValueError):
            self.ui.message("查看附件", paths, "s2")
        with self.assertRaises(ValueError):
            self.ui.message("", [], "s2")
        self.assertNotIn("uploads", short_title(self.ui.message("请分析数据", paths, "s1")))
        self.assertIn("data.csv", self.ui.chips(paths))
        display = self.ui.display_message(self.ui.message("分析数据", paths, "s1"))
        self.assertIn("data.csv", display)
        self.assertNotIn("uploads/", display)

    def test_projects_api_and_backward_compatible_session_creation(self):
        settings = Settings(data_dir=Path(self.temp.name), model="demo", skill_roots=())
        with TestClient(create_app(settings, with_ui=False)) as client:
            project = client.post("/api/projects", json={"name": "图学习"}).json()
            first = client.post("/api/sessions", params={"project_id": project["id"]}).json()
            client.post("/api/sessions", params={"project_id": project["id"]})
            self.assertEqual(len(client.get("/api/projects").json()[0]["sessions"]), 2)
            self.assertEqual(client.get("/api/sessions/"+first["id"]).status_code, 200)


class ProjectSummaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name))
        self.s1 = self.store.session("s1", project_id="p1")

    async def finish(self, session, text, answer, title="设计长期记忆消融实验", bad_quote=False):
        sid = session["id"]
        self.store.append(sid, HumanMessage(content=text))
        mid = self.store.append(sid, AIMessage(content=answer))
        class Model:
            async def ainvoke(inner, messages):
                payload = json.loads(messages[-1].content)
                self.assertEqual(payload["first_question"], "研究长期记忆机制") if sid == "s1" else None
                return AIMessage(content=json.dumps({"title": title, "updates": [], "project_summary": {
                    "text": answer, "evidence": [{"message_id": mid, "quote": "forged source" if bad_quote else answer}]
                }}, ensure_ascii=False))
        await MemoryManager(self.store, session).finish_turn(text, answer, [], Model())

    async def test_title_stays_first_question_and_shared_summary_is_versioned(self):
        await self.finish(self.s1, "研究长期记忆机制", "建议做记忆消融，尚未验证。")
        self.assertEqual(self.store.get_session("s1")["title"], "设计长期记忆消融实验")
        memories = self.store.memories("project_memory", "local/p1")
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["content"]["status"], "unverified_summary")
        self.assertEqual(memories[0]["sources"][0]["role"], "ai")
        await self.finish(self.s1, "改用三个随机种子", "计划调整为三个种子，仍未执行。", title="不应覆盖首问标题")
        current = self.store.memories("project_memory", "local/p1")
        self.assertEqual(current[0]["version"], 2)
        self.assertEqual(len(current), 1)
        self.assertEqual(self.store.get_session("s1")["title"], "设计长期记忆消融实验")
        same = self.store.session("s2", project_id="p1")
        self.assertIn("三个种子", str(self.store.injected_memory(same)))
        other = self.store.session("s3", project_id="p2")
        self.assertNotIn("三个种子", str(self.store.injected_memory(other)))
        self.assertEqual(len(self.store.history("s1")), 4)
        await self.finish(same, "方法设计", "候选方法尚需实验验证。")
        self.assertEqual(len(self.store.memories("project_memory", "local/p1")), 2)

    async def test_invalid_evidence_or_failed_summary_never_invents_shared_memory(self):
        await self.finish(self.s1, "研究长期记忆机制", "未验证的结果", bad_quote=True)
        self.assertEqual(self.store.memories("project_memory"), [])
        class Broken:
            async def ainvoke(self, messages):
                raise RuntimeError("offline")
        await MemoryManager(self.store, self.s1).finish_turn("研究长期记忆机制", "未验证的结果", [], Broken())
        self.assertTrue(self.store.memories("session_memory"))
        self.assertEqual(len(self.store.history("s1")), 2)
        self.assertTrue(any(e["kind"] == "memory_warning" for e in self.store.events("s1")))

    async def test_stop_cancels_worker_and_allows_same_session_to_continue(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()
        class SlowModel:
            def bind_tools(self, tools):
                return self
            async def ainvoke(self, messages):
                started.set()
                try:
                    await asyncio.Future()
                finally:
                    cancelled.set()
        settings = Settings(data_dir=Path(self.temp.name), model="test:model", extract_memory=False, skill_roots=())
        service = AgentService(settings, model_factory=lambda _: SlowModel())
        self.addAsyncCleanup(service.close)
        events = []
        async def consume():
            async for event in service.stream("cancel", "start"):
                events.append(event["type"])
        consumer = asyncio.create_task(consume())
        await asyncio.wait_for(started.wait(), 5)
        self.assertTrue(await service.cancel_turn("cancel"))
        await asyncio.wait_for(consumer, 5)
        self.assertTrue(cancelled.is_set())
        self.assertNotIn("done", events)
        self.assertFalse(service.locks["cancel"].locked())
        self.assertNotIn("cancel", service.stream_tasks)
        self.assertEqual(len(service.store.history("cancel")), 1)
        resumed = await service.run_turn("cancel", "continue", settings=settings.with_overrides(model="demo"))
        self.assertIn("离线", resumed["content"])
        fast = service.stream("fast", "hello", settings=settings.with_overrides(model="demo"))
        self.assertEqual((await anext(fast))["type"], "token")
        # A finished worker may still have unconsumed UI events in its queue.
        self.assertTrue(await service.cancel_turn("fast"))
        self.assertEqual([e async for e in fast], [])
        app = create_app(settings, service=service)
        blocks = next(r.app.get_blocks() for r in app.routes if hasattr(getattr(r, "app", None), "get_blocks"))
        submit = next(f.fn for f in blocks.fns.values() if getattr(f.fn, "__name__", "") == "submit")
        view = {"generation": 0}
        started.clear()
        updates = submit("start", "ui_cancel", "default", "test:model", "", False, [], view)
        await anext(updates)  # Initial UI update.
        self.assertEqual([u async for u in updates], [])  # SSE owns subsequent progress.
        await asyncio.wait_for(started.wait(), 5)
        stop = next(f.fn for f in blocks.fns.values() if getattr(f.fn, "__name__", "") == "stop_turn")
        result = await stop("ui_cancel", "default", view)
        self.assertTrue(result[0].startswith("已停止"))
        self.assertEqual(service.runs.db.latest("ui_cancel")["status"], "stopped")
        self.assertFalse(service.locks["ui_cancel"].locked())


if __name__ == "__main__":
    unittest.main()
