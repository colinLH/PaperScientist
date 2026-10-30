"""Isolated software regression tests; no research corpus or live account is used."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import graph_sync as graph
from obsidian_sync import Vault, front, split_note
from runtime_support import file_lock, load_config, validate_config

HERE = Path(__file__).resolve().parent


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="skill test 中文 ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.config = self.base / "runtime/config.json"
        self.work = self.base / "runtime"
        self.root = self.base / "vault/AI安全"
        self.cli("init", "--vault", str(self.base / "vault"), "--workspace", str(self.work), "--timezone", "Asia/Singapore")
        self.c = load_config(self.config)

    def cli(self, *args, ok=True):
        result = subprocess.run([sys.executable, str(HERE / "workflow.py"), "--config", str(self.config), *args],
                                capture_output=True, text=True, encoding="utf-8")
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        # Graphify may write progress before the CLI JSON. Only callers needing
        # structured output use commands whose stdout is JSON exclusively.
        return result

    def report(self):
        result = json.loads(self.cli("obsidian", "new-report", "--date", "2026-10-30", "--title", "临时合成报告").stdout)
        report = Path(result["path"])
        meta, _ = split_note(report.read_text(encoding="utf-8"))
        meta["complete"] = True
        report.write_text(front(meta) + "# 合成软件测试材料\n\n" + "仅验证软件行为，不是论文研究证据。" * 20, encoding="utf-8")
        pdf = self.root / "附件/PDF/synthetic.pdf"
        pdf.write_bytes(b"%PDF-1.7\n% synthetic header fixture, not a research paper\n")
        record = {"title": "Synthetic Software Test Paper", "arxiv_id": "2501.12345v2", "read_version": "synthetic-v2",
                  "source_url": "https://example.org/synthetic-paper", "collected_on": "2026-10-30",
                  "pdf_local": "AI安全/附件/PDF/synthetic.pdf", "report_file": str(report.relative_to(self.base / "vault"))}
        candidates = self.base / "candidates.json"
        graph.write(candidates, [record])
        return report, record, candidates

    def prepare(self):
        report, record, candidates = self.report()
        self.cli("obsidian", "register", "--file", str(candidates))
        plan_path = self.base / "plan.json"
        self.cli("obsidian", "plan", "--output", str(plan_path))
        row = graph.read(plan_path)["needs_extraction"][0]
        extraction = {"source_id": row["source_id"], "content_hash": row["content_hash"], "complete": True,
                      "nodes": [
                          {"id": "p", "label": "合成测试论文", "kind": "paper", "category": "attack", "full_title": record["title"], "identity": {"arxiv": "2501.12345"}},
                          {"id": "d1", "label": "合成领域一", "kind": "domain", "category": "attack"},
                          {"id": "d2", "label": "合成领域二", "kind": "domain", "category": "attack"},
                          {"id": "s", "label": "临时合成报告", "kind": "source", "category": "attack"}],
                      "edges": []}
        for source, target in [("p", "d1"), ("p", "d2"), ("s", "p")]:
            extraction["edges"].append({"source": source, "target": target, "relation": "references", "label": "合成测试关系",
                                        "confidence": "INFERRED", "confidence_score": 0.5, "basis": "合成软件测试",
                                        "evidence": "仅用于软件回归测试", "evidence_url": "https://example.org/synthetic-paper", "source_location": "合成软件测试材料"})
        extraction_path = self.base / "extraction.json"
        graph.write(extraction_path, extraction)
        batch = self.base / "batch.json"
        graph.write(batch, [{"fetch_file": row["fetch_file"], "extraction_file": str(extraction_path)}])
        return report, plan_path, batch, extraction_path

    def apply(self):
        prepared = self.prepare()
        self.cli("graph", "apply", "--batch", str(prepared[2]))
        return prepared

    def test_fresh_initialization_is_repeatable_and_does_not_create_schedules(self):
        self.cli("init", "--vault", str(self.base / "vault"), "--workspace", str(self.work), "--timezone", "Asia/Singapore")
        self.assertTrue(json.loads(self.cli("doctor").stdout)["ok"])
        self.assertFalse((self.work / "automations.json").exists())
        prompts = json.loads(self.cli("prompts").stdout)
        self.assertFalse(prompts["schedules_created"])
        self.assertIn(str(self.config), prompts["prompts"]["daily"])
        self.assertFalse((self.work / "work/sync/pending-publication.json").exists())

    def test_same_day_resume_and_idempotent_registration(self):
        report, _, candidates = self.report()
        resumed = json.loads(self.cli("obsidian", "new-report", "--date", "2026-10-30", "--title", "另一个标题").stdout)
        self.assertEqual(resumed["path"], str(report))
        self.cli("obsidian", "register", "--file", str(candidates))
        result = json.loads(self.cli("obsidian", "register", "--file", str(candidates)).stdout)
        self.assertEqual(result["registered"], 0)
        self.assertEqual(result["already_registered"], 1)
        record = graph.read(candidates)[0]
        record.update(title="New title but same paper", arxiv_id="2501.12345v9")
        graph.write(candidates, [record])
        self.cli("obsidian", "register", "--file", str(candidates), ok=False)
        self.assertEqual(len(graph.read(self.root / "系统/collection-index.json")["records"]), 1)

    def test_full_pipeline_persists_provenance_canvas_and_detects_unfinished_export(self):
        report, plan, batch, _ = self.apply()
        self.cli("obsidian", "finalize", "--plan", str(plan))
        self.cli("obsidian", "validate")
        status = json.loads(self.cli("obsidian", "plan", "--output", str(self.base / "next.json")).stdout)
        self.assertEqual(status["needs_extraction"], [])
        self.assertTrue(status["needs_export"])
        self.cli("graph", "export")
        self.assertTrue(graph.export_current(graph.paths(self.work)))
        validation = graph.read(self.root / "系统/last-validation.json")
        self.assertFalse(validation["failures"])
        db_validation = graph.read(self.root / "系统/图数据库/validation.json")
        self.assertTrue(db_validation["reopened"])
        self.assertEqual(db_validation["provenance_assertions"], 3)
        index = graph.read(self.root / "系统/collection-index.json")["records"][0]
        self.assertEqual(index["pdf_local"], "AI安全/附件/PDF/synthetic.pdf")
        generation = graph.read(self.work / "work/sync/current.json")
        self.cli("graph", "apply", "--batch", str(batch))
        self.assertEqual(generation, graph.read(self.work / "work/sync/current.json"))
        (self.work / "outputs/ai-safety-graph.zip").unlink()
        self.assertFalse(graph.export_current(graph.paths(self.work)))
        self.cli("graph", "export")
        self.assertTrue(graph.export_current(graph.paths(self.work)))
        self.assertFalse((self.work / "work/sync/pending-publication.json").exists())

    def test_finalize_failure_does_not_ack_and_can_resume(self):
        _, plan, _, _ = self.apply()
        v = Vault(self.c)
        v.managed(self.root / "user.md", "generated")
        note = self.root / "user.md"
        note.write_text(note.read_text(encoding="utf-8").replace("generated", "manual edit"), encoding="utf-8")
        self.cli("obsidian", "finalize", "--plan", str(plan), ok=False)
        self.assertEqual(Vault(self.c).ledger["sources"], {})
        self.assertIn("manual edit", note.read_text(encoding="utf-8"))
        # Explicitly restore only this fixture's deliberate edit, simulating a
        # user-resolved conflict; production recovery must not clear hashes.
        note.write_text(note.read_text(encoding="utf-8").replace("manual edit", "generated"), encoding="utf-8")
        self.cli("obsidian", "finalize", "--plan", str(plan))
        self.assertEqual(len(Vault(self.c).ledger["sources"]), 1)

    def test_personal_text_survives_and_canvas_edits_are_preserved(self):
        v = Vault(self.c)
        note = self.root / "personal.md"
        v.managed(note, "first")
        note.write_text(note.read_text(encoding="utf-8") + "个人笔记\n", encoding="utf-8")
        v.managed(note, "second")
        self.assertIn("个人笔记", note.read_text(encoding="utf-8"))
        canvas = self.root / "05-图谱/test.canvas"
        v.managed_json(canvas, {"nodes": [], "edges": []})
        graph.write(canvas, {"nodes": [{"id": "human"}], "edges": []})
        before = canvas.read_bytes()
        with self.assertRaises(ValueError):
            v.managed_json(canvas, {"nodes": [], "edges": []})
        self.assertEqual(canvas.read_bytes(), before)
        self.assertTrue(v.plan(self.base / "conflict.json")["errors"])

    def test_missing_complete_duplicate_id_and_missing_source_do_not_enter_plan(self):
        report, _, _ = self.report()
        meta, body = split_note(report.read_text(encoding="utf-8"))
        del meta["complete"]
        report.write_text(front(meta) + body, encoding="utf-8")
        v = Vault(self.c)
        self.assertFalse(v.plan(self.base / "draft.json")["needs_extraction"])
        meta["complete"] = True
        report.write_text(front(meta) + body, encoding="utf-8")
        clone = report.with_name("duplicate.md")
        clone.write_text(report.read_text(encoding="utf-8"), encoding="utf-8")
        plan = v.plan(self.base / "duplicate.json")
        self.assertTrue(plan["errors"])
        self.assertFalse(plan["needs_extraction"])
        clone.unlink()
        v.ledger["sources"][meta["source_id"]] = {"path": str(report)}
        report.unlink()
        self.assertTrue(v.plan(self.base / "missing.json")["errors"])

    def test_revision_keeps_history_and_other_source_evidence(self):
        _, plan_path, _, extraction_path = self.prepare()
        row = graph.read(plan_path)["needs_extraction"][0]
        doc = graph.source(graph.read(row["fetch_file"]))
        extraction = graph.read(extraction_path)
        state = graph.blank()
        graph.add_revision(state, doc, extraction)
        second = {**doc, "id": "e" * 32}
        graph.add_revision(state, second, {**extraction, "source_id": second["id"]})
        revised = {**doc, "hash": "revised", "body": doc["body"] + " revision"}
        new = {**extraction, "content_hash": "revised", "edges": []}
        graph.add_revision(state, revised, new)
        self.assertEqual(len(state["sources"][doc["id"]]["revisions"]), 2)
        self.assertEqual(len(graph.aggregate(state)["edges"]), 3)
        self.assertFalse(graph.add_revision(state, revised, new))

    def test_invalid_batch_does_not_replace_current_generation(self):
        _, _, batch, extraction_path = self.apply()
        before = (self.work / "work/sync/current.json").read_bytes()
        extraction = graph.read(extraction_path)
        extraction["content_hash"] = "mismatched"
        graph.write(extraction_path, extraction)
        self.cli("graph", "apply", "--batch", str(batch), ok=False)
        self.assertEqual(before, (self.work / "work/sync/current.json").read_bytes())

    def test_report_edit_after_plan_prevents_stale_apply(self):
        report, _, batch, _ = self.prepare()
        report.write_text(report.read_text(encoding="utf-8") + "\n更新后的证据\n", encoding="utf-8")
        self.cli("graph", "apply", "--batch", str(batch), ok=False)
        self.assertFalse((self.work / "work/sync/current.json").exists())

    def test_wrong_publication_receipt_does_not_clear_pending(self):
        self.c["site"] = {"enabled": True, "project_id": "synthetic-project", "url": "https://example.org/private"}
        graph.write(self.config, self.c)
        self.apply()
        pending_path = self.work / "work/sync/pending-publication.json"
        pending = graph.read(pending_path)
        pending.update(commit_sha="synthetic-commit", version_id="synthetic-version")
        graph.write(pending_path, pending)
        receipt = {**pending, "status": "succeeded", "deployment_id": "synthetic-deployment", "url": self.c["site"]["url"], "project_id": "wrong-project"}
        path = self.base / "receipt.json"
        graph.write(path, receipt)
        self.cli("graph", "mark-published", "--receipt", str(path), ok=False)
        self.assertTrue(pending_path.exists())

    def test_conflicting_identity_and_missing_evidence_rejected(self):
        state = graph.blank()
        node = {"id": "p", "label": "Test", "kind": "paper", "full_title": "Full title", "identity": {"arxiv": "2501.12345"}}
        original = graph.identity(state, node)
        self.assertEqual(original, graph.identity(state, {**node, "identity": {"arxiv": "2501.12345v2"}}))
        with self.assertRaises(ValueError):
            graph.identity(state, {**node, "identity": {"arxiv": "2501.99999"}})
        _, plan, _, xfile = self.prepare()
        row = graph.read(plan)["needs_extraction"][0]
        extraction = graph.read(xfile)
        extraction["edges"][0].pop("evidence_url")
        with self.assertRaises(ValueError):
            graph.add_revision(graph.blank(), graph.source(graph.read(row["fetch_file"])), extraction)

    def test_path_escape_and_concurrent_writer_rejected(self):
        for prefix in ("../escape", "/tmp/escape", "..", "a/b"):
            with self.assertRaises(ValueError):
                validate_config({**self.c, "prefix": prefix})
        with file_lock(self.work / "work/sync/pipeline.lock"):
            self.cli("obsidian", "new-report", "--date", "2026-10-30", "--title", "locked", ok=False)
        self.assertFalse(list((self.root / "01-报告").glob("*.md")))


if __name__ == "__main__":
    unittest.main()
