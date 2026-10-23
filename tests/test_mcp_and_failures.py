import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from paperscientist.config import Settings
from paperscientist.context import ContextManager, ContextOverflow
from paperscientist.mcp import load_tools
from paperscientist.runtime import AgentService
from paperscientist.tools import ToolSet


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_mcp_stdio_preserves_nested_schema(self):
        with tempfile.TemporaryDirectory() as temp:
            config=Path(temp)/"mcp.json"
            config.write_text(json.dumps({"mcpServers":{"fixture":{
                "transport":"stdio","command":sys.executable,
                "args":[str(Path(__file__).with_name("mcp_fixture.py"))],
                "allowed_tools":["inspect_evidence"]}}}))
            tools,errors=await load_tools(config)
            self.assertFalse(errors,errors)
            self.assertEqual(len(tools),1)
            result=await tools[0].ainvoke({"options":{"mode":"brief","count":2}})
            self.assertTrue(result["ok"],result)
            self.assertIn("brief",str(result))
            with self.assertRaises(Exception):
                await tools[0].ainvoke({"options":{"mode":"invalid","count":0}})

    async def test_summary_failure_does_not_commit_checkpoint(self):
        class BrokenSummary:
            async def ainvoke(self,messages):
                raise RuntimeError("temporary model failure")
        with tempfile.TemporaryDirectory() as temp:
            service=AgentService(Settings(data_dir=Path(temp),context_tokens=4096,output_tokens=512))
            session=service.store.session("summary")
            for i in range(10):
                service.store.append("summary",HumanMessage(content="evidence "*1800))
                service.store.append("summary",AIMessage(content="pending"))
            before=len(service.store.history("summary"))
            with self.assertRaises(RuntimeError):
                await ContextManager(service.store,session,service.settings).build("system",BrokenSummary())
            self.assertIsNone(service.store.checkpoint("summary"))
            self.assertEqual(len(service.store.history("summary")),before)
            await service.close()

    async def test_cancel_child_and_recover_after_restart(self):
        class Slow:
            def bind_tools(self,tools): return self
            async def ainvoke(self,messages):
                await asyncio.sleep(60)
                return AIMessage(content="done")
        with tempfile.TemporaryDirectory() as temp:
            cfg=Settings(data_dir=Path(temp),extract_memory=False)
            service=AgentService(cfg,lambda _:Slow())
            session=service.store.session("parent")
            tools={t.name:t for t in ToolSet(service,session,cfg,service.scheduler).tools}
            child=await tools["spawn_agent"].ainvoke({"task_name":"slow","message":"test","role":"reviewer"})
            await asyncio.sleep(.1)
            cancelled=await tools["cancel_agent"].ainvoke({"target":child["id"]})
            self.assertEqual(cancelled["status"],"cancelled")
            child["status"]="running"
            service.store.save_agent(child)
            service.store.recover_agents()
            self.assertEqual(service.store.agents("parent")[0]["status"],"interrupted")
            await service.close()
