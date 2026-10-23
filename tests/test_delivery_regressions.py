import json
import tempfile
import unittest
import warnings
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

from paperscientist.artifacts import draw_framework, figure_fonts, run_python, validate_manuscript
from paperscientist.config import Settings
from paperscientist.refine import refine_history
from paperscientist.runtime import AgentService
from paperscientist.store import Store


class Model:
    def bind_tools(self, tools): return self
    async def ainvoke(self, messages):
        return AIMessage(content="",tool_calls=[{"name":"list_files","args":{},"id":"loop"}])


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.service=AgentService(Settings(data_dir=Path(self.tmp.name),model="test:model",extract_memory=False,max_steps=1),model_factory=lambda _:Model())
        self.store=self.service.store
        self.session=self.store.session("session")

    async def asyncTearDown(self):
        await self.service.close()
        self.tmp.cleanup()

    async def test_budget_stop_is_not_reported_as_completed(self):
        result=await self.service.run_turn("session","inspect files")
        self.assertEqual(result["stop_reason"],"budget_exhausted")
        self.assertTrue(any(e["kind"]=="turn_paused" for e in self.store.events("session")))

    async def test_generated_files_registered_and_script_hash_is_pre_execution(self):
        import hashlib
        script=self.store.file("session","generate.py")
        script.write_text("from pathlib import Path\nPath('result.csv').write_text('x,y\\n1,2\\n')\nPath(__file__).write_text('# modified')\n")
        digest=hashlib.sha256(script.read_bytes()).hexdigest()
        run=await run_python(self.store,"session","generate.py",True)
        self.assertEqual(run["script_sha256"],digest)
        self.assertTrue(any(Path(a["path"]).name=="result.csv" for a in run["generated_artifacts"]))

    async def test_loaded_skill_survives_unrelated_events(self):
        self.store.event("session","skill_loaded",{"name":"paper-polish"})
        for i in range(110): self.store.event("session","tool_result",{"i":i})
        self.assertEqual(self.store.active_skills("session"),[{"name":"paper-polish"}])

    async def test_manuscript_detects_missing_inputs_figures_and_citations(self):
        main=self.store.file("session","main.tex")
        main.write_text(r"\input{missing}\includegraphics{missing_plot}\cite{fake}\ref{absent}")
        result=validate_manuscript(self.store,"session","main.tex")
        self.assertEqual(result["status"],"error")
        self.assertEqual(len(result["errors"]),4)

    async def test_offline_refinement_requires_user_evidence_and_is_dry_by_default(self):
        self.store.append("session",HumanMessage(content="我长期研究图学习。"))
        class Extractor:
            async def ainvoke(self,messages):
                return AIMessage(content=json.dumps({"updates":[
                    {"kind":"user_profile","content":"研究图学习","evidence_quote":"长期研究图学习"},
                    {"kind":"user_profile","content":"偏好GPU","evidence_quote":"偏好GPU"}]}))
        report=await refine_history(self.store,"session",Extractor())
        self.assertEqual(len(report["proposals"]),1)
        self.assertEqual(report["rejected"],1)
        self.assertFalse(self.store.memories())
        await refine_history(self.store,"session",Extractor(),apply=True)
        self.assertEqual(len(self.store.memories()),1)

    async def test_chinese_framework_font(self):
        if figure_fonts()[0]=="DejaVu Sans":
            self.skipTest("No CJK font installed on this host")
        with warnings.catch_warnings(record=True) as captured:
            paths=draw_framework(self.store,"session",[{"id":"a","label":"证据保留"},{"id":"b","label":"实验评估"}],
                                 [{"source":"a","target":"b"}],"科研流程（合成验证）")
        self.assertFalse(any("Glyph" in str(w.message) for w in captured))
        self.assertTrue(all(p.is_file() for p in paths))


if __name__=="__main__": unittest.main()
