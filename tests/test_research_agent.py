import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from paperscientist.api import create_app
from paperscientist.artifacts import assemble_manuscript, plot_results, run_python
from paperscientist.config import Settings
from paperscientist.context import ContextManager, ContextOverflow, micro_compact, message_tokens
from paperscientist.memory import MemoryManager
from paperscientist.migrate import import_chats
from paperscientist.runtime import AgentService
from paperscientist.skills import SkillCatalog
from paperscientist.store import Store
from paperscientist.tools import ToolSet


class FakeModel:
    def __init__(self,responses=None):
        self.responses = list(responses or [AIMessage(content="完成：基于已记录证据。")])
        self.inputs = []
        self.tools = []

    def bind_tools(self,tools):
        self.tools = tools
        return self

    async def ainvoke(self,messages):
        self.inputs.append(messages)
        if "Compress research conversation" in str(messages[0].content):
            return AIMessage(content="目标：保留研究证据。已完成文献比较。下一步：设计消融；尚无测量结论。")
        return self.responses.pop(0) if self.responses else AIMessage(content="完成。")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name))
        self.session = self.store.session("s1",project_id="p1")

    def test_append_versions_and_scope(self):
        mid = self.store.append("s1",HumanMessage(content="我长期研究图学习，喜欢用中文讨论。"))
        memory = MemoryManager(self.store,self.session)
        first = memory.remember("user_profile","研究图学习","我长期研究图学习")
        memory.remember("user_profile","研究图学习；中文讨论","喜欢用中文讨论",first["id"])
        latest = self.store.memories("user_profile","local")
        self.assertEqual(latest[0]["version"],2)
        self.assertEqual(latest[0]["sources"][0]["message_id"],mid)
        self.assertEqual(len(self.store.memories(versions=True)),2)
        other_project = self.store.session("s2",project_id="p2")
        self.assertEqual(self.store.injected_memory(other_project)[0]["id"],first["id"])
        other_user = self.store.session("s3",user_id="another",project_id="p1")
        self.assertEqual(self.store.injected_memory(other_user),[])
        with self.assertRaises(ValueError):
            memory.remember("user_profile","invented","no such statement")
        with self.assertRaises(ValueError):
            self.store.put_memory("user_profile","another",{},[],first["id"])

    def test_automation_and_session_memory_not_generally_injected(self):
        self.store.put_memory("automation_memory","local/task1",{"run_count":1},[])
        self.store.put_memory("session_memory","local/p1/s1",{"intent":"detail"},[])
        self.assertEqual(self.store.injected_memory(self.session),[])
        self.assertEqual(self.store.injected_memory(self.session,"task1")[0]["kind"],"automation_memory")

    def test_workspace_traversal_and_session_ownership(self):
        for path in ("../outside.txt", "../../.env", str(Path(self.temp.name)/"outside.txt")):
            with self.assertRaises(ValueError):
                self.store.file("s1",path)
        with self.assertRaises(ValueError):
            self.store.session("s1",user_id="other",project_id="p1")

    def test_skill_progressive_loading_and_migration(self):
        root = Path(self.temp.name)/"skills"
        (root/"one").mkdir(parents=True)
        (root/"one"/"SKILL.md").write_text("---\nname: one\ndescription: metadata\n---\nSECRET BODY",encoding="utf-8")
        catalog = SkillCatalog([root])
        self.assertNotIn("SECRET BODY",catalog.listing())
        self.assertIn("SECRET BODY",catalog.load("one"))
        with self.assertRaises(ValueError):
            catalog.load("one","../../outside.txt")
        source=Path(self.temp.name)/"old"
        source.mkdir()
        (source/"a.json").write_text(json.dumps({"turns":[{"user":"hello","assistant":"answer"}]}))
        self.assertEqual(import_chats(self.store,source,apply=False)["imported"],0)
        self.assertEqual(import_chats(self.store,source,apply=True)["imported"],1)
        self.assertEqual(import_chats(self.store,source,apply=True)["skipped"],1)


class AsyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(data_dir=Path(self.temp.name),extract_memory=False,allow_execution=True)
        self.service = AgentService(self.settings)
        self.store = self.service.store
        self.session = self.store.session("session")
        self.addAsyncCleanup(self.service.close)

    def tool(self,name):
        return next(t for t in ToolSet(self.service,self.session,self.settings,self.service.scheduler).tools if t.name==name)

    async def test_dynamic_tools_multi_turn_and_recovery(self):
        model = FakeModel([
            AIMessage(content="",tool_calls=[{"name":"remember","args":{"kind":"user_profile","content":"长期研究图学习","evidence_quote":"我长期研究图学习"},"id":"call1"}]),
            AIMessage(content="已记住你的研究兴趣。"),AIMessage(content="我们继续图学习方向。")])
        self.service.model_factory=lambda _:model
        first = await self.service.run_turn("session","我长期研究图学习")
        second = await self.service.run_turn("session","继续")
        self.assertIn("图学习",second["content"])
        self.assertEqual(len([m for _,m in self.store.history("session") if m.type=="human"]),2)
        self.assertIn("长期研究图学习",str(model.inputs[-1][0].content))
        self.store.append("session",AIMessage(content="",tool_calls=[{"name":"write_file","args":{},"id":"interrupted"}]))
        self.service.repair_tool_pairs("session")
        self.assertEqual(self.store.history("session")[-1][1].tool_call_id,"interrupted")
        self.assertEqual(self.store.history("session")[-1][1].status,"error")

    async def test_micro_compact_keeps_pairs_and_current_continuations(self):
        history=[]
        for i in range(7):
            history += [HumanMessage(content=f"task {i}"),AIMessage(content="",tool_calls=[{"name":"read_file","args":{},"id":str(i)}]),
                        ToolMessage(content="large payload "*1000,tool_call_id=str(i)),AIMessage(content=f"answer {i}")]
        history.append(HumanMessage(content="继续"))
        compacted=micro_compact(history)
        self.assertEqual(history[2].content,"large payload "*1000)
        pending=set()
        for m in compacted:
            if m.type=="ai": pending.update(c["id"] for c in m.tool_calls)
            elif m.type=="tool":
                self.assertIn(m.tool_call_id,pending)
                pending.remove(m.tool_call_id)
        self.assertFalse(pending)
        self.assertEqual(next(m for m in compacted if m.type=="tool" and m.tool_call_id=="6").content,history[-3].content)
        self.assertLess(len(str(compacted)),len(str(history)))

    async def test_sync_summary_keeps_raw_history_and_resumes(self):
        for i in range(9):
            self.store.append("session",HumanMessage(content=f"Question {i}: "+"research evidence uncertainty "*450))
            self.store.append("session",AIMessage(content="Result pending "+"hypothesis "*200))
        self.store.append("session",HumanMessage(content="继续设计消融"))
        before=len(self.store.history("session"))
        context=ContextManager(self.store,self.session,self.settings.with_overrides(context_tokens=7000,output_tokens=512))
        built=await context.build("You are a researcher",FakeModel())
        self.assertIsNotNone(self.store.checkpoint("session"))
        self.assertEqual(len(self.store.history("session")),before)
        self.assertTrue(any("尚无测量结论" in str(m.content) for m in built))
        built_again=await context.build("You are a researcher",FakeModel())
        self.assertIn("继续设计消融",str(built_again[-1].content))

    async def test_large_child_state_and_legacy_restore_are_bounded_without_data_loss(self):
        agent = {"id":"large-child", "parent_id":"session", "task_name":"design", "role":"design",
                 "status":"interrupted", "result":"bounded result "*8000,
                 "capabilities":{"inherited_harnesses":[{"name":"implementation_tests"}]},
                 "artifacts":[{"id":str(i), "path":f"source/{i}.py", "kind":"source",
                               "metadata":{"evidence":"large receipt "*1000}} for i in range(150)]}
        self.store.save_agent(agent)
        mid = self.store.append("session", HumanMessage(content="Retain the failed design checks."))
        # Emulate a checkpoint from before coordination state was bounded.
        restore = {"subagents":[agent], "artifacts":[]}
        self.store.save_checkpoint("session", mid, "Design remains interrupted; tests must pass.", restore)
        context = ContextManager(self.store, self.session, self.settings.with_overrides(context_tokens=7000, output_tokens=512))
        prompt = self.service.system_prompt(self.session, self.settings.with_overrides(skill_roots=()))
        self.assertNotIn("large receipt", prompt)
        built = await context.build("Research coordinator", FakeModel())
        self.assertLess(message_tokens(built), 6000)
        self.assertIn("large-child", str(built))
        self.assertIn("interrupted", str(built))
        self.assertEqual(self.store.get_agent("large-child"), agent)
        self.assertEqual(self.store.checkpoint("session")["restore"], restore)

    async def test_child_evidence_pagination_keeps_all_results_and_importable_artifacts(self):
        sid = "evidence-child"
        self.store.session(sid, parent_id="session")
        registered = []
        for i in range(23):
            path = self.store.file(sid, f"evidence-{i}.txt")
            path.write_text(f"evidence {i}")
            registered.append(self.store.artifact(sid, path, "source"))
        result = "complete evidence "*1600
        agent = {"id":sid, "parent_id":"session", "task_name":"evidence", "role":"literature",
                 "status":"completed", "result":result, "artifacts":self.store.artifacts(sid)}
        self.store.save_agent(agent)
        listing = await self.tool("wait_agent").ainvoke({"target":sid,"timeout":0})
        self.assertLess(len(json.dumps(listing)), 6000)
        self.assertEqual(listing[0]["artifact_count"],23)
        ids, offset = [], 0
        while offset is not None:
            page = await self.tool("read_agent").ainvoke({"target":sid,"artifact_offset":offset,"history_limit":0})
            ids.extend(a["id"] for a in page["artifacts"])
            offset = page["next_artifact_offset"]
        self.assertEqual(set(ids), {a["id"] for a in registered})
        pieces, offset = [], 0
        while offset is not None:
            page = await self.tool("read_agent").ainvoke({"target":sid,"result_offset":offset,"history_limit":0})
            pieces.append(page["result"])
            offset = page["next_result_offset"]
        self.assertEqual("".join(pieces),result)
        imported = await self.tool("import_agent_artifact").ainvoke({"target":sid,"artifact_id":ids[-1],"destination":"imported.txt"})
        self.assertTrue(self.store.file("session",imported["path"]).is_file())
        self.assertEqual(self.store.get_agent(sid),agent)

    async def test_code_results_plotting_and_provenance(self):
        await self.tool("write_file").ainvoke({"path":"experiment.py","content":"from pathlib import Path\nPath('results.csv').write_text('method,score,sd\\nbaseline,0.5,0.02\\nmethod,0.7,0.03\\n')\nprint('synthetic smoke test')\n"})
        run=await self.tool("run_python").ainvoke({"path":"experiment.py"})
        self.assertEqual(run["exit_code"],0,run["stderr"])
        result=await self.tool("record_experiment").ainvoke({"claim_id":"smoke","result_path":"results.csv","provenance":"measured","evaluation_question":"Does the pipeline produce a readable result?","run_id":run["run_id"],"notes":"synthetic smoke data"})
        self.assertEqual(result["metadata"]["run_id"],run["run_id"])
        figures=await self.tool("plot_results").ainvoke({"csv_path":"results.csv","x":"method","y":"score","error":"sd","kind":"bar","title":"Synthetic pipeline validation"})
        self.assertEqual({a["kind"] for a in figures["artifacts"]}, {"figure", "plot_code", "figure_contract"})
        self.assertEqual(len([a for a in figures["artifacts"] if a["kind"] == "figure"]), 3)
        self.store.file("session","results.csv").write_text("method,score\nforged,99\n")
        with self.assertRaises(ValueError):
            await self.tool("record_experiment").ainvoke({"claim_id":"x","result_path":"results.csv","provenance":"measured","evaluation_question":"test","run_id":run["run_id"]})
        with self.assertRaises(PermissionError):
            await run_python(self.store,"session","experiment.py",False)

    async def test_manuscript_verified_citations(self):
        paper=self.store.add_paper(self.session,{"title":"Test Paper","authors":["A. Author"],"year":2025,"url":"https://example.org/paper","provider":"test"})
        folder=assemble_manuscript(self.store,self.session,"Test & Review","A draft",{"Introduction":r"See \cite{"+paper["id"]+"}."},[paper["id"]])
        self.assertTrue((folder/"main.tex").is_file())
        self.assertIn(paper["id"],(folder/"references.bib").read_text())
        with self.assertRaises(ValueError):
            assemble_manuscript(self.store,self.session,"Test","",{"Results":r"\cite{madeup}"},[])

    async def test_subagent_context_and_resume(self):
        models=[]
        def factory(_):
            m=FakeModel(); models.append(m); return m
        self.service.model_factory=factory
        spawned=await self.tool("spawn_agent").ainvoke({"task_name":"review","message":"Critique a memory study","role":"reviewer"})
        status=await self.tool("wait_agent").ainvoke({"target":spawned["id"],"timeout":10})
        self.assertEqual(status[0]["status"],"completed",status)
        self.assertNotIn("spawn_agent",[t.name for t in models[0].tools])
        self.assertNotIn("remember",[t.name for t in models[0].tools])
        await self.tool("followup_task").ainvoke({"target":"review","message":"Now check ablations"})
        status=await self.tool("wait_agent").ainvoke({"target":"review","timeout":10})
        self.assertEqual(status[0]["status"],"completed")
        self.assertEqual(len([m for _,m in self.store.history(spawned["id"]) if m.type=="human"]),2)


class APITests(unittest.TestCase):
    def test_sse_sessions_upload_export_and_ui(self):
        with tempfile.TemporaryDirectory() as temp:
            settings=Settings(data_dir=Path(temp),model="demo")
            app=create_app(settings,with_ui=True)
            with TestClient(app) as client:
                self.assertEqual(client.get("/").status_code,200)
                self.assertEqual(client.get("/api/health").json()["status"],"ok")
                response=client.post("/api/chat/web_session",json={"message":"我想探索科研方向"})
                self.assertIn("event: done",response.text)
                data=client.get("/api/sessions/web_session").json()
                self.assertEqual(len(data["messages"]),2)
                upload=client.post("/api/sessions/web_session/upload",files={"file":("data.csv",b"x,y\n1,2\n","text/csv")})
                self.assertEqual(upload.status_code,200)
                self.assertEqual(client.get("/api/artifacts/"+upload.json()["id"]).status_code,200)
                self.assertEqual(client.get("/api/sessions/web_session/export").status_code,200)


if __name__ == "__main__":
    unittest.main()
