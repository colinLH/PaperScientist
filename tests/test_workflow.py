import tempfile
import unittest
from pathlib import Path

from paperscientist.run_store import RunStore
from paperscientist.store import Store
from paperscientist.timeline import Timeline
from paperscientist.workflow import session_workflow


class PaperProgressTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = Store(Path(directory.name))
        self.timeline = Timeline(self.store, None)
        self.runs = RunStore(self.store)
        self.store.session("a")
        self.store.session("b")

    def statuses(self, sid):
        workflow = session_workflow(self.store, sid, self.runs.latest(sid))
        return {s["id"]: s["status"] for s in workflow["steps"]}

    def test_legacy_session_evidence_is_scoped_and_can_revisit(self):
        # The same project has a writing plan; a sibling session has never worked on it.
        self.store.update_project(self.store.get_session("a"), {"stage": "writing"})
        self.store.event("a", "tool_result", {"name":"update_research_plan", "status":"success",
                                               "result":{"stage":"experiment"}})
        self.assertEqual(self.statuses("a")["evaluation"], "current")
        self.assertEqual(set(self.statuses("b").values()), {"pending"})
        run = self.runs.create("a", "revisit the literature", {})
        self.runs.update(run["id"], status="running", preview="正在调用 search_papers")
        self.assertEqual(self.statuses("a")["literature"], "active")
        self.assertEqual(self.statuses("a")["evaluation"], "visited")

    def test_waiting_report_survives_reopen_and_completion_needs_a_delivered_manuscript(self):
        run = self.runs.create("a", "draft", {})
        rid = run["id"]
        self.timeline.begin("a", rid, "draft")
        self.timeline.emit("a", rid, "workflow", {"stage":"writing","completed":["idea","delivery"]})
        self.runs.update(rid, status="waiting_input")
        self.store = Store(self.store.root)
        self.assertEqual(self.statuses("a")["writing"], "current")
        self.assertEqual(self.statuses("a")["idea"], "done")
        self.assertEqual(self.statuses("a")["delivery"], "pending")
        pdf = self.store.file("a", "main.pdf")
        pdf.write_bytes(b"fixture")
        self.store.artifact("a", pdf, "manuscript_pdf")
        self.runs.update(rid, status="completed", outcome={"artifacts":["notes.md"]})
        self.assertEqual(self.statuses("a")["delivery"], "pending")
        self.runs.update(rid, status="completed", outcome={"artifacts":["main.pdf"]})
        self.assertEqual(self.statuses("a")["delivery"], "done")
        later = self.runs.create("a", "new request", {})
        self.runs.update(later["id"], status="running")
        self.assertNotIn("active", self.statuses("a").values())
        self.assertEqual(self.statuses("a")["delivery"], "done")
