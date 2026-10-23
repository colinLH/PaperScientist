import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from paperscientist.context import ContextManager
from paperscientist.config import Settings
from paperscientist.runtime import AgentService
from paperscientist.workspace_actions import WorkspaceActions
from langchain_core.tools import tool


def call(name, args, ident):
    return {"name": name, "args": args, "id": ident, "type": "tool_call"}


class Model:
    def __init__(self, replies):
        self.replies, self.inputs = list(replies), []

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.inputs.append(messages)
        return self.replies.pop(0)


class DurableRuns(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cfg = Settings(data_dir=Path(self.temp.name), model="test:model", skill_roots=(), extract_memory=False)

    def service(self, model):
        service = AgentService(self.cfg, model_factory=lambda _: model)
        self.addAsyncCleanup(service.close)
        return service

    async def done(self, service, rid):
        await asyncio.wait_for(service.runs.tasks[rid], 15)
        return service.runs.db.get(rid)

    async def test_interrupt_restart_answer_and_contiguous_tool_messages(self):
        model = Model([AIMessage(content="", tool_calls=[
            call("write_file", {"path": "before.txt", "content": "before interrupt"}, "write1"),
            call("ask_user_question", {"question": "实验范围？", "options": ["CPU", "硬件"]}, "ask1"),
            call("read_file", {"path": "before.txt"}, "read1")])])
        first = self.service(model)
        run = await first.runs.start("s1", "完成实验")
        rid = run["id"]
        result = await self.done(first, rid)
        self.assertEqual(result["status"], "waiting_input", result)
        self.assertEqual(first.store.file("s1", "before.txt").read_text(), "before interrupt")
        await first.close()
        model2 = Model([AIMessage(content="", tool_calls=[call("finish_research", {"summary": "完成 CPU 实验", "artifacts": ["before.txt"], "limitations": []}, "finish1")])])
        second = self.service(model2)
        await second.runs.recover()
        self.assertEqual(second.runs.db.latest("s1")["pending"]["question_id"], "ask1")
        with self.assertRaises(ValueError):
            await second.runs.answer(rid, "stale", "CPU")
        await second.runs.answer(rid, "ask1", "CPU")
        result = await self.done(second, rid)
        self.assertEqual(result["status"], "completed", result)
        history = [m for _, m in second.store.history("s1")]
        self.assertEqual([m.type for m in history[:6]], ["human", "ai", "tool", "tool", "tool", "human"])
        self.assertEqual(sum(getattr(m, "tool_call_id", "") == "write1" for m in history), 1)
        self.assertIn("CPU", str(model2.inputs[0]))
        await WorkspaceActions(second).execute("session", "s1", "delete", confirmed=True)
        self.assertIsNone(second.runs.db.get(rid))

    async def test_shutdown_restarts_model_node_without_duplicate_user_message(self):
        ready = asyncio.Event()
        class Slow(Model):
            async def ainvoke(self, messages):
                ready.set()
                await asyncio.Future()
        first = self.service(Slow([]))
        run = await first.runs.start("s1", "完成任务")
        await asyncio.wait_for(ready.wait(), 10)
        await first.close()
        self.assertEqual(first.runs.db.get(run["id"])["status"], "recovering")
        second = self.service(Model([AIMessage(content="", tool_calls=[call("finish_research", {"summary": "完成", "artifacts": [], "limitations": []}, "finish")])]))
        await second.runs.recover()
        result = await self.done(second, run["id"])
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(sum(m.type == "human" for _, m in second.store.history("s1")), 1)

    async def test_budget_pause_continue_and_browser_independence(self):
        model = Model([AIMessage(content="还在工作"), AIMessage(content="", tool_calls=[call("finish_research", {"summary": "全部完成", "artifacts": [], "limitations": []}, "finish")])])
        service = self.service(model)
        run = await service.runs.start("s1", "完整研究", settings=self.cfg.with_overrides(max_steps=1))
        self.assertFalse(await service.cancel_turn("s1"))  # Disconnect/navigation only cancels legacy streams.
        result = await self.done(service, run["id"])
        self.assertEqual(result["status"], "paused", result)
        await service.runs.continue_run(run["id"])
        result = await self.done(service, run["id"])
        self.assertEqual(result["status"], "completed", result)
        service.runs.db.preference(session_id="s1", project_id="default")
        self.assertEqual(AgentService(self.cfg).runs.db.preference()["session_id"], "s1")

    async def test_no_progress_pauses_early_and_continue_resets_guard(self):
        model = Model([AIMessage(content='已经回复，但没有下一步操作') for _ in range(4)])
        service = self.service(model)
        run = await service.runs.start('s1', '持续研究', settings=self.cfg.with_overrides(max_steps=60))
        result = await self.done(service, run['id'])
        self.assertEqual(result['status'], 'paused')
        self.assertEqual(result['outcome']['reason'], 'no_progress')
        self.assertEqual(len(model.inputs), 2)
        await service.runs.continue_run(run['id'])
        result = await self.done(service, run['id'])
        self.assertEqual(result['status'], 'paused')
        self.assertEqual(len(model.inputs), 4)

    async def test_plain_chat_completes_without_forcing_extra_model_calls(self):
        model = Model([AIMessage(content='完整回答')])
        service = self.service(model)
        run = await service.runs.start('s1', '解释概念', continuous=False)
        result = await self.done(service, run['id'])
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(model.inputs), 1)

    async def test_progress_without_content_is_visible_ordered_and_durable(self):
        model = Model([
            AIMessage(content='', tool_calls=[call('report_progress', {'update':'先检查现有记录，再整理结果。'}, 'p1'),
                                             call('write_file', {'path':'note.md','content':'verified'}, 'w1')]),
            AIMessage(content='', tool_calls=[call('report_progress', {'update':'已写入记录，接下来核对交付文件。'}, 'p2'),
                                             call('finish_research', {'summary':'完成','artifacts':['note.md'],'limitations':[]}, 'f1')])])
        service = self.service(model)
        run = await service.runs.start('s1', '整理记录')
        result = await self.done(service, run['id'])
        self.assertEqual(result['status'], 'completed')
        items = service.timeline.snapshot('s1')['turns'][0]['items']
        visible = [i for i in items if i.get('text')]
        self.assertEqual([i['text'] for i in visible], ['先检查现有记录，再整理结果。','已写入记录，接下来核对交付文件。','完成'])
        self.assertLess(next(i for i,x in enumerate(items) if x['id']=='progress-p1'),next(i for i,x in enumerate(items) if x['id']=='w1'))
        self.assertFalse(any(x.get('name')=='report_progress' for x in items))

    async def test_progress_only_does_not_bypass_no_progress_guard(self):
        model = Model([AIMessage(content='', tool_calls=[call('report_progress', {'update':'正在准备'}, 'p'+str(i))]) for i in range(3)])
        service = self.service(model)
        run = await service.runs.start('s1', '完成任务')
        self.assertEqual((await self.done(service, run['id']))['status'], 'paused')
        self.assertEqual(len(model.inputs), 2)

    async def test_truncated_tool_call_never_writes_and_resume_uses_complete_output(self):
        partial = AIMessage(content="", tool_calls=[call("write_file", {"path": "bad.py", "content": "def partial("}, "cut")], response_metadata={"finish_reason": "length"})
        complete = AIMessage(content="", tool_calls=[call("finish_research", {"summary": "recovered", "artifacts": [], "limitations": []}, "done")])
        service = self.service(Model([partial, complete]))
        run = await service.runs.start("s1", "write complete source")
        result = await self.done(service, run["id"])
        self.assertEqual(result["status"], "completed")
        self.assertFalse(service.store.file("s1", "bad.py").exists())
        self.assertFalse(any(getattr(m, "tool_calls", None) and m.tool_calls[0]["id"] == "cut" for _, m in service.store.history("s1")))

    async def test_incomplete_model_retry_is_bounded(self):
        partial = AIMessage(content="incomplete", response_metadata={"finish_reason": "length"})
        model = Model([partial, partial, partial])
        service = self.service(model)
        run = await service.runs.start("s1", "complete task")
        self.assertEqual((await self.done(service, run["id"]))["status"], "error")
        self.assertEqual(len(model.inputs), 3)

    async def test_stale_run_controls_do_not_affect_later_run(self):
        service = self.service(Model([]))
        service.store.session("s1")
        old = service.runs.db.create("s1", "old", {})
        service.runs.db.update(old["id"], status="stopped")
        new = service.runs.db.create("s1", "new", {})
        with self.assertRaises(ValueError):
            await service.runs.continue_run(old["id"])
        with self.assertRaises(ValueError):
            await service.runs.stop("s1", expected_run_id=old["id"])
        self.assertEqual(service.runs.db.get(new["id"])["status"], "queued")

    async def test_recovery_repairs_crash_between_run_creation_and_input_receipt(self):
        service = self.service(Model([AIMessage(content="", tool_calls=[call("finish_research", {"summary": "done", "artifacts": [], "limitations": []}, "finish")])]))
        service.store.session("s1")
        settings = {k: getattr(self.cfg, k) for k in ("model", "context_tokens", "output_tokens", "max_steps", "max_subagents", "tool_timeout", "allow_execution", "extract_memory")}
        run = service.runs.db.create("s1", "recover exact objective", {"continuous": True, "settings": settings})
        await service.runs.recover()
        self.assertEqual((await self.done(service, run["id"]))["status"], "completed")
        self.assertEqual([m.content for _, m in service.store.history("s1") if m.type == "human"], ["recover exact objective"])

    async def test_single_long_turn_compacts_without_breaking_tool_pairs(self):
        service = self.service(Model([]))
        session = service.store.session("long")
        service.store.append("long", HumanMessage(content="Exact user objective: evaluate real firmware only"))
        for index in range(28):
            service.store.append("long", AIMessage(content="", tool_calls=[call("read_file", {"path": "evidence.txt"}, str(index))]))
            service.store.append("long", ToolMessage(content="evidence uncertainty "*200, tool_call_id=str(index)))
        class Summary:
            async def ainvoke(self, messages):
                return AIMessage(content="Real firmware objective preserved. Evidence inspected; conclusions pending.")
        context = ContextManager(service.store, session, self.cfg.with_overrides(context_tokens=7000, output_tokens=512))
        for _ in range(2):
            result = await context.build("Research", Summary())
            self.assertTrue(any(m.type == "human" and "Exact user objective" in m.content for m in result))
            pending = set()
            for message in result:
                if message.type == "ai":
                    pending.update(c["id"] for c in message.tool_calls)
                elif message.type == "tool":
                    self.assertIn(message.tool_call_id, pending)
                    pending.remove(message.tool_call_id)
            self.assertFalse(pending)
        self.assertIsNotNone(service.store.checkpoint("long"))
        self.assertEqual(len(service.store.history("long")), 57)

    async def test_uncertain_effect_is_not_replayed_and_followup_waits_for_tool_group(self):
        started = asyncio.Event()
        effects = []
        @tool
        async def local_effect() -> dict:
            """Perform a local test effect then simulate loss of its completion receipt."""
            effects.append("effect")
            started.set()
            await asyncio.Future()
        model = Model([AIMessage(content="", tool_calls=[call("local_effect", {}, "effect1")])])
        with patch("paperscientist.runs.ToolSet", return_value=SimpleNamespace(tools=[local_effect])):
            first = self.service(model)
            run = await first.runs.start("s1", "Test recovery")
            await asyncio.wait_for(started.wait(), 10)
            await first.close()
            second = self.service(Model([AIMessage(content="", tool_calls=[call("finish_research", {"summary": "Test completed", "artifacts": [], "limitations": ["Effect outcome remains unconfirmed"]}, "done")])]))
            second.runs.db.enqueue(run["id"], "Operator follow-up")
            await second.runs.recover()
            result = await self.done(second, run["id"])
            self.assertEqual(result["status"], "completed", result)
            self.assertEqual(effects, ["effect"])
            history = [m for _, m in second.store.history("s1")]
            self.assertEqual([m.type for m in history[:4]], ["human", "ai", "tool", "human"])
            self.assertIn("未自动重复调用", history[2].content)
            self.assertEqual(history[2].status, "error")


if __name__ == "__main__":
    unittest.main()
