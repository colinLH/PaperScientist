import asyncio
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
import gradio as gr
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from paperscientist.api import create_app
from paperscientist.config import Settings
from paperscientist.runtime import AgentService
from paperscientist.store import Store
from paperscientist.workspace_actions import WorkspaceActions


class WorkspaceActionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(data_dir=Path(self.temp.name), model="demo", skill_roots=())
        self.service = AgentService(self.settings)
        self.addAsyncCleanup(self.service.close)
        self.store = self.service.store
        self.actions = WorkspaceActions(self.service)
        self.project = self.store.create_project("记忆研究")['id']
        self.session = self.store.session("s1", project_id=self.project)
        self.store.append("s1", HumanMessage(content="比较长期记忆"))
        self.store.append("s1", AIMessage(content="建议进行消融实验"))

    async def test_metadata_persists_and_archive_preserves_history(self):
        await self.actions.execute("session", "s1", "rename", "请保留这个完整自定义名称。")
        self.assertEqual(self.store.get_session("s1")["title"], "请保留这个完整自定义名称。")
        self.assertTrue(self.store.has_generated_title("s1"))
        for action, value in (("pin", ""), ("unread", ""), ("section", "待阅读")):
            await self.actions.execute("session", "s1", action, value)
        restarted = AgentService(self.settings)
        try:
            meta = WorkspaceActions(restarted).metadata("session", "s1")
            self.assertEqual(meta, {"pinned": True, "unread": True, "section": "待阅读"})
        finally:
            await restarted.close()
        await self.actions.execute("session", "s1", "archive")
        self.assertEqual(self.actions.groups()[0]["sessions"], [])
        self.assertEqual(len(self.actions.groups(True)[0]["sessions"]), 1)
        self.assertEqual(len(self.store.history("s1")), 2)
        with self.assertRaises(ValueError):
            self.store.session("s1", project_id=self.project)

        await self.actions.execute("project", self.project, "archive")
        self.assertEqual(self.actions.groups(), [])
        await self.actions.execute("project", self.project, "archive")
        self.assertTrue(self.actions.metadata("session", "s1")["archived"])
        await self.actions.execute("session", "s1", "archive")
        self.assertEqual(self.actions.groups()[0]["sessions"][0]["id"], "s1")

    async def test_fork_copies_tool_pairs_and_uploads_without_changing_source(self):
        file = self.store.file("s1", "uploads/data.csv")
        file.parent.mkdir()
        file.write_text("x,y\n1,2\n")
        self.store.artifact("s1", file, "upload")
        self.store.append("s1", AIMessage(content="", tool_calls=[{"id": "call_1", "name": "read", "args": {"path": str(file)}}]))
        self.store.append("s1", ToolMessage(content=str(file), tool_call_id="call_1"))
        self.store.append("s1", AIMessage(content="数据已读取"))
        result = await self.actions.execute("session", "s1", "fork")
        new = result["navigate"]
        self.assertIsNone(self.store.get_session(new)["parent_id"])
        self.assertEqual(len(self.store.history(new)), 5)
        self.assertEqual(self.store.history(new)[3][1].tool_call_id, "call_1")
        self.assertNotIn(str(file), self.store.history(new)[3][1].content)
        fork_file = self.store.file(new, "uploads/data.csv")
        self.assertEqual(fork_file.read_text(), file.read_text())
        self.assertNotEqual(self.store.artifacts(new)[0]["id"], self.store.artifacts("s1")[0]["id"])
        fork_file.write_text("independent")
        self.assertIn("1,2", file.read_text())
        await self.actions.execute("session", "s1", "delete", confirmed=True)
        self.assertEqual(len(self.store.history(new)), 5)
        self.assertTrue(fork_file.exists())

    async def test_delete_scopes_children_files_memory_versions_and_shares(self):
        self.store.session("child", project_id=self.project, parent_id="s1")
        other = self.store.session("s2", project_id="other")
        private = self.store.session("private", user_id="other", project_id=self.project)
        for sid in ("s1", "child", "s2", "private"):
            self.store.file(sid, "keep.txt").write_text(sid)
        ref = [{"session_id": "s1", "message_id": self.store.history("s1")[0][0]}]
        mem = self.store.put_memory("project_memory", "local/"+self.project, {"text": "旧摘要"}, ref)
        self.store.put_memory("project_memory", "local/"+self.project, {"text": "新摘要"}, ref, memory_id=mem["id"])
        self.store.put_memory("user_profile", "local", {"text": "独立用户偏好"}, [])
        self.store.put_memory("project_memory", "other/"+self.project, {"text": "其他用户"}, [])
        share = await self.actions.execute("session", "s1", "share")
        with self.assertRaises(ValueError):
            await self.actions.execute("project", self.project, "delete")
        await self.actions.execute("project", self.project, "delete", confirmed=True)
        self.assertIsNone(self.store.get_session("s1"))
        self.assertIsNone(self.store.get_session("child"))
        self.assertFalse((self.store.root/"workspaces/s1").exists())
        self.assertEqual(self.store.get_session("s2"), other)
        self.assertEqual(self.store.get_session("private"), private)
        self.assertEqual(len(self.store.memories()), 2)
        self.assertEqual(self.store.memories(owner="local/"+self.project, versions=True), [])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM shares").fetchone()[0], 0)
        with self.assertRaises(ValueError):
            self.store.session("new-stale-tab", project_id=self.project)
        with self.assertRaises(ValueError):
            self.store.session("s1", project_id=self.project)

    async def test_delete_cancels_live_stream_and_does_not_recreate_rows(self):
        started = asyncio.Event()
        async def run(sid, message, **kwargs):
            self.store.append(sid, HumanMessage(content=message))
            started.set()
            await asyncio.sleep(30)
            self.store.append(sid, AIMessage(content="must not persist"))
        self.service.run_turn = run
        stream = self.service.stream("s1", "start")
        consumer = asyncio.create_task(anext(stream))
        await started.wait()
        await self.actions.execute("session", "s1", "delete", confirmed=True)
        await asyncio.gather(consumer, return_exceptions=True)
        await stream.aclose()
        self.assertIsNone(self.store.get_session("s1"))
        self.assertEqual(self.store.history("s1"), [])
        self.assertEqual(self.store.events("s1"), [])
        with self.assertRaises(ValueError):
            self.store.append("s1", AIMessage(content="stale callback"))
        self.store.event("s1", "ui_stop_requested", {})
        self.assertEqual(self.store.events("s1"), [])

    async def test_api_shares_are_safe_snapshots_revocable_and_exportable(self):
        self.store.append("s1", AIMessage(content='<script>alert("x")</script>'))
        with TestClient(create_app(self.settings, service=self.service, with_ui=False)) as client:
            route = "/api/workspace/action"
            body = {"kind": "session", "target": "s1", "action": "share"}
            link = client.post(route, json=body).json()["url"]
            self.store.append("s1", HumanMessage(content="快照之后的新消息"))
            page = client.get(link)
            self.assertEqual(page.status_code, 200)
            self.assertIn('&lt;script&gt;', page.text)
            self.assertNotIn('<script>', page.text)
            self.assertNotIn('快照之后的新消息', page.text)
            self.assertIn('default-src', page.headers['content-security-policy'])
            self.assertIn('快照之后的新消息', client.get('/api/sessions/s1/markdown').text)
            client.post(route, json={**body, "action": "unshare"})
            self.assertEqual(client.get(link).status_code, 404)
            self.assertEqual(client.post(route, json={**body, "action": "delete"}).status_code, 400)
            self.store.session("foreign", user_id="other")
            self.assertEqual(client.post(route, json={**body, "target": "foreign"}).status_code, 400)

    async def test_ui_delete_moves_selection_and_archived_history_is_read_only(self):
        app = create_app(self.settings, service=self.service)
        blocks = next(r.app.get_blocks() for r in app.routes if hasattr(getattr(r, "app", None), "get_blocks"))
        callback = next(f.fn for f in blocks.fns.values() if getattr(f.fn, "__name__", "") == "sidebar_action")
        view = {"generation": 0, "session_id": "s1"}
        await self.actions.execute("session", "s1", "archive")
        selected = await callback("unused", self.project, view, [], True, gr.EventData(None, {"action": "select", "kind": "session", "id": "s1"}))
        self.assertEqual(selected[0], "s1")
        self.assertFalse(selected[13]["interactive"])
        self.assertFalse(selected[17]["interactive"])
        deleted = await callback("s1", self.project, view, [], True, gr.EventData(None, {"action": "delete", "kind": "project", "id": self.project, "confirmed": True}))
        self.assertNotEqual(deleted[0], "s1")
        self.assertNotEqual(deleted[1], self.project)
        self.assertIn('data-session="'+deleted[0]+'"', deleted[2])
        self.assertNotIn('data-session="s1"', deleted[2])
        self.assertTrue(deleted[17]["interactive"])
        self.assertIn("永久删除", deleted[3])
        self.assertIsNone(self.store.get_session("s1"))
        start = next(f.fn for f in blocks.fns.values() if getattr(f.fn, "__name__", "") == "start_chat")
        created = await start(deleted[1], deleted[0], view)
        self.assertFalse(created[-1])  # A new chat always returns navigation to active projects.

    async def test_composer_swaps_send_and_stop_when_restoring_run_states(self):
        app = create_app(self.settings, service=self.service)
        blocks = next(r.app.get_blocks() for r in app.routes if hasattr(getattr(r, 'app', None), 'get_blocks'))
        select = next(f.fn for f in blocks.fns.values() if getattr(f.fn, '__name__', '') == 'sidebar_action')
        poll = next(f.fn for f in blocks.fns.values() if getattr(f.fn, '__name__', '') == 'poll_run')
        run = self.service.runs.db.create('s1', '验证状态', {'settings': {'allow_execution': False}})
        for state in ('running', 'waiting_input', 'paused', 'completed'):
            self.service.runs.db.update(run['id'], status=state)
            view = {'generation':0,'session_id':'s1'}
            selected = await select('s1', self.project, view, [], False, gr.EventData(None, {'action':'select','kind':'session','id':'s1'}))
            busy = state in {'running', 'waiting_input'}
            self.assertEqual(selected[17]['visible'], not busy)
            self.assertEqual(selected[18]['visible'], busy)
            updates = poll('s1', self.project, view, False)
            self.assertEqual(updates[11]['visible'], not busy)
            self.assertEqual(updates[12]['visible'], busy)


if __name__ == '__main__':
    unittest.main()
