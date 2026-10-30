import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from paperscientist import artifacts, evidence
from paperscientist.config import Settings
from paperscientist.runtime import AgentService
from paperscientist.skills import SkillCatalog
from paperscientist.store import Store
from paperscientist.tools import ToolSet


class SkillIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / "data")
        self.session = self.store.session("s")
        self.store.update_project(self.session, {"claims": [
            {"id": "C1", "hypothesis": "Test hypothesis", "evaluation_question": "Does A change B?", "evidence_ids": []}]})

    def test_namespaces_search_pagination_and_lazy_body(self):
        for provider in ("one", "two"):
            root = self.root / "skills" / provider
            root.mkdir(parents=True)
            (root / ".source.json").write_text(json.dumps({
                "id": provider, "url": "https://example.com", "commit": "test", "topics": "review"}))
            for i in range(65):
                folder = root / "nested" / f"review-{i:02}"
                folder.mkdir(parents=True)
                (folder / "SKILL.md").write_text("---\nname: shared\ndescription: peer review evidence\n---\nBODY_NOT_METADATA")
        catalog = SkillCatalog([self.root / "skills"])
        self.assertEqual(len(catalog.skills), 130)
        self.assertNotIn("BODY_NOT_METADATA", catalog.listing())
        page = catalog.search("审稿", source="two", limit=50)
        self.assertEqual(page["total"], 65)
        tail = catalog.search("审稿", source="two", offset=page["next_offset"])
        self.assertEqual(len(tail["skills"]), 15)
        self.assertIn("BODY_NOT_METADATA", catalog.load("two:review-64"))

    def test_shared_resources_and_staging_cannot_escape_or_overwrite(self):
        base = self.root / "skills" / "provider"
        package = base / "sample"
        package.mkdir(parents=True)
        (base / ".source.json").write_text(json.dumps({"id":"provider","url":"https://example.com","commit":"test"}))
        (package / "SKILL.md").write_text("---\nname: sample\ndescription: test\n---\nhello")
        (package / "script.py").write_text("raise RuntimeError('Must not execute on stage')")
        (base / "_source" / "shared").mkdir(parents=True)
        (base / "_source" / "shared" / "reference.md").write_text("preserved shared reference")
        catalog = SkillCatalog([self.root / "skills"])
        self.assertIn("preserved", catalog.load("provider:sample", "@source/shared/reference.md"))
        for path in ("../../outside.txt", "@source/../../outside.txt"):
            with self.assertRaises(ValueError):
                catalog.load("provider:sample", path)
        result = catalog.stage("provider:sample", self.root / "staged")
        self.assertEqual(result["files"], 2)
        self.assertTrue((self.root / "staged" / "script.py").exists())
        with self.assertRaises(ValueError):
            catalog.stage("provider:sample", self.root / "staged")

    def test_evidence_rejects_fabricated_quote_and_detects_changed_source(self):
        paper = self.store.add_paper(self.session, {"title":"Controlled experiment", "abstract":"Intervention A did not improve outcome B.", "url":"https://example.com/paper"})
        with self.assertRaises(ValueError):
            evidence.record_evidence(self.store,self.session,"C1","paper",paper["id"],"A always improves B","unsupported","supports","")
        saved = evidence.record_evidence(self.store,self.session,"C1","paper",paper["id"],
            "Intervention A did not improve outcome B.","No observed improvement","contradicts","abstract")
        report = evidence.audit_research(self.store,self.session)
        self.assertIn(saved["id"], report["claims"][0]["contradictions"])
        self.assertEqual(report["status"], "needs_review")
        self.store.add_paper(self.session, {**paper, "abstract":"A corrected abstract without the original statement."})
        self.assertTrue(any(i["type"] == "stale_evidence" for i in evidence.audit_research(self.store,self.session)["issues"]))

    def test_synthetic_figure_is_not_declared_ready(self):
        path = self.store.file("s", "results.csv")
        path.write_text("method,score,error\nA,0.6,0.1\nB,0.7,0.2\n")
        self.store.artifact("s",path,"experiment_result",{"claim_id":"C1","provenance":"synthetic"})
        report = evidence.figure_report(self.store,"s",path,error="error")
        self.assertEqual(report["provenance"], "synthetic")
        self.assertEqual(len(report["reporting_gaps"]), 4)
        self.assertNotEqual(report["publication_readiness"], "passed")
        path.write_text("method,score,error\nA,nan,0.1\n")
        with self.assertRaises(ValueError):
            artifacts.plot_results(self.store,"s","results.csv","method","score",error="error")

    def test_drawio_preserves_unicode_labels_and_graph_with_reserved_ids(self):
        nodes = [{"id":"0","label":"检索 <证据> & 校验"}, {"id":"1","label":"Review"}]
        path = self.store.file("s","framework.drawio")
        artifacts.write_drawio(path,nodes,[{"source":"0","target":"1"}],{"0":(0,0),"1":(3.3,0)},"研究流程")
        cells = ET.parse(path).findall(".//mxCell")
        vertices = [c for c in cells if c.get("vertex") == "1"]
        self.assertEqual(vertices[0].get("value"), nodes[0]["label"])
        edge = next(c for c in cells if c.get("edge") == "1")
        self.assertIn(edge.get("source"), {v.get("id") for v in vertices})
        self.assertEqual(len({c.get("id") for c in cells}), len(cells))


class ToolIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_isolated_review_uses_frozen_packet_without_parent_memory(self):
        from langchain_core.messages import AIMessage
        class Reviewer:
            def __init__(self):
                self.inputs = []
                self.tools = []
            def bind_tools(self, tools):
                self.tools = [t.name for t in tools]
                return self
            async def ainvoke(self, messages):
                self.inputs.append(messages)
                return AIMessage(content="Review complete; bounded to the source packet.")
        with tempfile.TemporaryDirectory() as directory:
            cfg = Settings(data_dir=Path(directory), model="test:review", allow_execution=True,
                           extract_memory=False, skill_roots=())
            model = Reviewer()
            service = AgentService(cfg, model_factory=lambda _:model)
            try:
                parent = service.store.session("parent")
                service.store.update_project(parent, {"hidden_peer_findings":"PEER_CRITIQUE_SECRET"})
                service.store.put_memory("user_profile","local",{"text":"PROFILE_SECRET"},[])
                source = service.store.file("parent","manuscript.txt")
                source.write_text("Frozen original manuscript")
                artifact = service.store.artifact("parent",source,"manuscript")
                peer = service.store.file("parent","other_review.txt")
                peer.write_text("PEER_REPORT_SECRET")
                service.store.artifact("parent",peer,"review")
                spawn = next(t for t in service.scheduler.tools(parent,cfg) if t.name=="spawn_agent")
                child = await spawn.ainvoke({"task_name":"blind","message":"Assess validity only","role":"reviewer",
                                            "isolated_review":True,"artifact_ids":[artifact["id"]]})
                source.write_text("Changed after snapshot")
                await service.scheduler.tasks[child["id"]]
                prompt = str(model.inputs)
                for secret in ("PEER_CRITIQUE_SECRET","PEER_REPORT_SECRET","PROFILE_SECRET"):
                    self.assertNotIn(secret,prompt)
                for tool in ("recall_memory","experience_recall","copy_parent_artifact","list_papers","audit_research",
                             "search_papers", "read_paper", "fetch_url", "web_search", "run_python", "spawn_agent"):
                    self.assertNotIn(tool,model.tools)
                packet = service.store.file(child["id"],child["review_packet"][0]["path"])
                self.assertEqual(packet.read_text(),"Frozen original manuscript")
                session = service.store.get_session(child["id"])
                from paperscientist.context import ContextManager
                restored = ContextManager(service.store, session, cfg).restore()
                self.assertEqual(restored["project"], {})
                self.assertEqual(restored["memory_refs"], [])
                tools = {t.name:t for t in ToolSet(service,session,cfg,child=True).tools}
                with self.assertRaises(PermissionError):
                    await tools["write_file"].ainvoke({"path":child["review_packet"][0]["path"],"content":"changed","overwrite":True})
                for name, args in [("list_files", {"scope":"project"}),
                                   ("read_file", {"scope":"project", "path":"secret.txt"})]:
                    with self.assertRaises(ValueError):
                        await tools[name].ainvoke(args)
            finally:
                await service.close()

    async def test_plot_contract_and_tool_schemas(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = Settings(data_dir=Path(directory), model="demo", skill_roots=())
            service = AgentService(cfg)
            try:
                session = service.store.session("s")
                tools = {t.name:t for t in ToolSet(service,session,cfg).tools}
                for t in tools.values():
                    self.assertIsInstance(t.args_schema.model_json_schema(), dict)
                service.store.file("s","data.csv").write_text("method,value,sd\nA,1.0,0.2\nB,1.5,0.3\n")
                output = await tools["plot_results"].ainvoke({"csv_path":"data.csv","x":"method","y":"value",
                    "error":"sd","kind":"bar","question":"Synthetic validation only","sample_size":3,
                    "n_definition":"synthetic seeds","uncertainty_definition":"synthetic SD"})
                self.assertIn("figure_contract", output)
                self.assertTrue(any(a["kind"]=="figure_contract" for a in output["artifacts"]))
                self.assertEqual(output["figure_contract"]["provenance"], "unverified")
                self.assertEqual(len(output["figure_contract"]["outputs"]), 4)
            finally:
                await service.close()


if __name__ == "__main__":
    unittest.main()
