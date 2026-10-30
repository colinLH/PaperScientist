"""Benchmark provenance and coverage checks, including a real local adapter run.

The parity fixture is synthetic and never represents a published benchmark score.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from paperscientist.artifacts import run_python
from paperscientist.benchmarks import (
    audit_benchmarks, collect_benchmark_source, discover_benchmarks,
    plan_benchmark, protect_benchmark_file, record_benchmark_result, register_benchmark, run_benchmark,
)
from paperscientist.store import Store


class BenchmarkHarness(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name))
        self.sid = "bench-test"
        self.store.session(self.sid)
        self.manifest = {
            "id": "parity-adapter-smoke", "title": "Synthetic parity adapter smoke",
            "version": "fixture-v1", "task": "Verify the local evaluation adapter only",
            "source_url": "https://github.com/colinLH/PaperScientist",
            "license": "test-fixture", "license_url": "https://github.com/colinLH/PaperScientist",
            "license_notes": "Locally authored six-case synthetic test; no external benchmark data.",
            "provenance": "local_synthetic", "splits": ["test"],
            "metrics": {"accuracy": "Exact parity label match over all planned cases, including failures"},
        }
        register_benchmark(self.store, self.sid, self.manifest)
        self.write("cases.json", [{"case_id": str(i), "split": "test", "x": i, "target": i % 2} for i in range(6)])
        self.script = '''import json
from pathlib import Path
cases = json.loads(Path("cases.json").read_text(encoding="utf-8"))
rows = []
for seed in [0, 1]:
    for method in ["parity", "always-one"]:
        for case in cases:
            # Predictions use only inputs; labels are compared by the harness.
            prediction = case["x"] % 2 if method == "parity" else 1
            rows.append(dict(case_id=case["case_id"], method=method, seed=seed,
                             status="ok", prediction=prediction))
Path("results.json").write_text(json.dumps(rows), encoding="utf-8")
'''
        self.store.file(self.sid, "evaluate.py").write_text(self.script, encoding="utf-8")
        self.protocol = {
            "decision": "selected", "rationale": "Tests the actual adapter execution and aggregation path",
            "claim": "The harness preserves evidence and computes parity accuracy", "task_match": "Local smoke only",
            "scope": "smoke", "split": "test", "adapter": "local_python", "script_path": "evaluate.py",
            "dataset_path": "cases.json", "result_path": "results.json", "case_ids": [str(i) for i in range(6)],
            "methods": ["parity", "always-one"], "seeds": [0, 1], "metrics": ["accuracy"],
            "evaluator_description": "Locally reviewed deterministic parity fixture; not an official suite grader",
            "limitations": "Synthetic six-case smoke; says nothing about scientific-agent benchmark performance",
            "budget": {"timeout_seconds": 20, "max_evaluations": 24, "hardware": "local CPU"},
        }

    def write(self, path, obj):
        self.store.file(self.sid, path).write_text(json.dumps(obj), encoding="utf-8")

    def plan(self, **changes):
        return plan_benchmark(self.store, self.sid, self.manifest["id"], {**self.protocol, **changes})

    def fixed_rows(self, rows):
        self.store.file(self.sid, "evaluate.py").write_text(
            "import json\nfrom pathlib import Path\n"
            f"Path('results.json').write_text({json.dumps(rows)!r}, encoding='utf-8')\n", encoding="utf-8")

    async def test_real_local_adapter_scores_and_restart_audit(self):
        plan = self.plan()
        result = await run_benchmark(self.store, self.sid, plan["plan_id"], True)
        summary = result["summary"]
        self.assertEqual(summary["expected"], 24)
        self.assertEqual(summary["observed"], 24)
        self.assertEqual(summary["scores"]["parity"]["accuracy"]["value"], 1.0)
        self.assertEqual(summary["scores"]["always-one"]["accuracy"]["value"], .5)
        self.assertTrue(summary["protocol_complete"])
        self.assertFalse(summary["official_benchmark_complete"])
        self.assertEqual(result["provenance"], "local_synthetic")
        restored = Store(Path(self.temp.name))
        self.assertTrue(audit_benchmarks(restored, self.sid)["all_selected_protocols_complete"])
        # A later run can overwrite its output; the audited evidence snapshot survives.
        self.write("results.json", [])
        self.assertTrue(audit_benchmarks(restored, self.sid)["all_selected_protocols_complete"])

    def test_discovery_is_conditional_and_persisted(self):
        result = discover_benchmarks("研究科研 agent 的科学发现能力", self.store, self.sid)
        self.assertIn("scienceagentbench", {x["id"] for x in result["candidates"]})
        self.assertTrue(self.store.file(self.sid, result["path"]).exists())
        self.assertEqual(discover_benchmarks("调节页面透明度")["candidates"], [])
        self.assertEqual(discover_benchmarks("program repair coding agent")["candidates"][0]["id"], "swe-bench")
        register_benchmark(self.store, self.sid, {**self.manifest, "id": "custom-domain", "keywords": ["marine acoustics"]})
        custom = discover_benchmarks("marine acoustics classification", self.store, self.sid)
        self.assertEqual(custom["candidates"][0]["id"], "custom-domain")

    async def test_revision_preserves_failed_history_and_requires_fresh_complete_run(self):
        old = self.plan(case_ids=["0", "1"])
        with self.assertRaises(ValueError):
            await run_benchmark(self.store, self.sid, old["plan_id"], True)
        old_bytes = self.store.file(self.sid, old["path"]).read_bytes()
        revised = self.plan(supersedes=[old["plan_id"]], revision_reason="Correct two-case coverage mismatch",
                            prior_exposure="Six-case pilot has already been observed")
        before = audit_benchmarks(self.store, self.sid)
        self.assertEqual(before["pending_plans"], [revised["plan_id"]])
        self.assertFalse(before["all_selected_protocols_complete"])
        await run_benchmark(self.store, self.sid, revised["plan_id"], True)
        after = audit_benchmarks(Store(Path(self.temp.name)), self.sid)
        self.assertTrue(after["all_selected_protocols_complete"], after)
        self.assertEqual(after["superseded_protocols"][0]["plan_id"], old["plan_id"])
        self.assertEqual(after["revisions"][0]["prior_exposure"], "Six-case pilot has already been observed")
        self.assertEqual(self.store.file(self.sid, old["path"]).read_bytes(), old_bytes)
        self.assertFalse(after["official_benchmark_complete"])

    async def test_revision_handles_changed_old_input_but_never_modified_result_receipt(self):
        old = self.plan()
        old_result = await run_benchmark(self.store, self.sid, old["plan_id"], True)
        self.store.file(self.sid, "evaluate.py").write_text(self.script + "# later change\n")
        revised = self.plan(supersedes=[old["plan_id"]], revision_reason="Correct evaluator",
                            prior_exposure="Exploratory rerun after observed pilot")
        await run_benchmark(self.store, self.sid, revised["plan_id"], True)
        audit = audit_benchmarks(self.store, self.sid)
        self.assertTrue(audit["all_selected_protocols_complete"], audit)
        self.assertFalse(audit["historical_integrity_valid"])
        self.assertTrue(any(r.get("historical_input_failure") for r in audit["results"]))
        self.store.file(self.sid, old_result["result_snapshot_path"]).write_text("[]")
        damaged = audit_benchmarks(self.store, self.sid)
        self.assertFalse(damaged["integrity_valid"])
        self.assertFalse(damaged["all_selected_protocols_complete"])

    def test_revision_rejects_scope_reduction_and_missing_exposure(self):
        old = self.plan()
        revision = dict(supersedes=[old["plan_id"]], revision_reason="Fix", prior_exposure="Pilot observed")
        for changes in ({"case_ids": ["0"]}, {"methods": ["parity"]}, {"seeds": [0]},
                        {"prior_exposure": ""}, {"decision": "not_applicable"},
                        {"supersedes": ["bench_missing"]}, {"supersedes": [old["plan_id"], old["plan_id"]]}):
            with self.subTest(changes=changes), self.assertRaises((ValueError, FileNotFoundError)):
                self.plan(**{**revision, **changes})
        self.write("other-cases.json", [{"case_id": str(i), "split": "test", "target": 0} for i in range(6)])
        with self.assertRaisesRegex(ValueError, "dataset_sha256"):
            self.plan(**revision, dataset_path="other-cases.json")

    def test_frozen_inputs_and_receipts_require_new_paths(self):
        self.write("dependency.json", {"setting": 1})
        plan = self.plan(input_paths=["dependency.json"])
        for path in ("evaluate.py", "cases.json", "dependency.json", plan["path"], plan["manifest_path"]):
            with self.subTest(path=path), self.assertRaises(PermissionError):
                protect_benchmark_file(self.store, self.sid, path)
        protect_benchmark_file(self.store, self.sid, "revision/evaluate.py")
        protect_benchmark_file(self.store, self.sid, "results.json")

    async def test_auxiliary_input_hash_is_checked_before_running(self):
        self.write("raw-data.json", [1, 2, 3])
        plan = self.plan(input_paths=["raw-data.json"])
        self.write("raw-data.json", [1, 2, 4])
        with self.assertRaisesRegex(ValueError, "Frozen benchmark input changed"):
            await run_benchmark(self.store, self.sid, plan["plan_id"], True)

    def test_manifest_requires_license_version_and_metric_definition(self):
        for changes in ({"version": "main"}, {"license": ""}, {"source_url": "file:///data"}, {"metrics": {"unknown": "score"}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                register_benchmark(self.store, self.sid, {**self.manifest, **changes})

    def test_justified_non_applicability_does_not_become_a_score(self):
        self.plan(decision="not_applicable", rationale="Does not measure paper novelty or prose quality")
        audit = audit_benchmarks(self.store, self.sid)
        self.assertEqual(len(audit["not_applicable"]), 1)
        self.assertFalse(audit["official_benchmark_complete"])
        self.assertFalse(audit["all_selected_protocols_complete"])

    async def test_execution_disabled_does_not_run_script(self):
        plan = self.plan()
        with self.assertRaises(PermissionError):
            await run_benchmark(self.store, self.sid, plan["plan_id"], False)
        self.assertFalse(self.store.file(self.sid, "results.json").exists())

    async def test_changed_inputs_invalidate_frozen_plan(self):
        plan = self.plan()
        self.store.file(self.sid, "evaluate.py").write_text("raise RuntimeError('changed')", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Frozen benchmark input changed"):
            await run_benchmark(self.store, self.sid, plan["plan_id"], True)

    async def test_post_hoc_protocol_is_rejected(self):
        run = await run_python(self.store, self.sid, "evaluate.py", True)
        plan = self.plan()
        with self.assertRaisesRegex(ValueError, "precede execution"):
            record_benchmark_result(self.store, self.sid, plan["plan_id"], "results.json", run["run_id"])

    async def test_modified_result_cannot_be_recorded_as_measured(self):
        plan = self.plan()
        run = await run_python(self.store, self.sid, "evaluate.py", True)
        self.write("results.json", [])
        with self.assertRaisesRegex(ValueError, "hash changed"):
            record_benchmark_result(self.store, self.sid, plan["plan_id"], "results.json", run["run_id"])

    async def test_modified_snapshot_is_detected_on_audit(self):
        plan = self.plan()
        result = await run_benchmark(self.store, self.sid, plan["plan_id"], True)
        self.write(result["result_snapshot_path"], [])
        audit = audit_benchmarks(self.store, self.sid)
        self.assertFalse(audit["all_selected_protocols_complete"])
        self.assertFalse(audit["results"][0]["valid"])

    async def test_partial_coverage_and_errors_do_not_disappear_from_denominator(self):
        rows = [{"case_id": "0", "method": "parity", "seed": 0, "status": "ok", "prediction": 0},
                {"case_id": "1", "method": "parity", "seed": 0, "status": "timeout"}]
        self.fixed_rows(rows)
        plan = self.plan()
        result = await run_benchmark(self.store, self.sid, plan["plan_id"], True)
        summary = result["summary"]
        self.assertFalse(summary["protocol_complete"])
        self.assertEqual(len(summary["missing"]), 22)
        self.assertEqual(len(summary["failed"]), 1)
        self.assertAlmostEqual(summary["scores"]["parity"]["accuracy"]["value"], 1 / 12)

    async def test_duplicate_or_unexpected_cases_are_rejected(self):
        for rows in (
            [{"case_id": "0", "method": "parity", "seed": 0, "status": "ok", "prediction": 0}] * 2,
            [{"case_id": "99", "method": "parity", "seed": 0, "status": "ok", "prediction": 0}],
        ):
            self.fixed_rows(rows)
            plan = self.plan()
            with self.assertRaisesRegex(ValueError, "Unexpected or duplicate"):
                await run_benchmark(self.store, self.sid, plan["plan_id"], True)

    async def test_failed_runner_is_not_a_completed_benchmark(self):
        self.store.file(self.sid, "evaluate.py").write_text("raise RuntimeError('fixture failure')", encoding="utf-8")
        plan = self.plan()
        result = await run_benchmark(self.store, self.sid, plan["plan_id"], True)
        self.assertEqual(result["status"], "execution_failed")
        self.assertFalse(result["protocol_complete"])
        audit = audit_benchmarks(self.store, self.sid)
        self.assertIn(plan["plan_id"], audit["pending_plans"])
        self.assertNotEqual(audit["attempts"][0]["exit_code"], 0)

    def test_scope_split_and_budget_are_enforced(self):
        for changes in ({"scope": "full_split"}, {"split": "train"}, {"budget": {"timeout_seconds": 10, "max_evaluations": 1, "hardware": "CPU"}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.plan(**changes)
        register_benchmark(self.store, self.sid, {**self.manifest, "provenance": "external"})
        with self.assertRaisesRegex(ValueError, "every case"):
            self.plan(scope="full_split", case_ids=["0"])

    async def test_collection_is_data_only_and_retains_provenance(self):
        with patch("paperscientist.benchmarks.fetch_public", new=AsyncMock(return_value=(b"[]", "application/json", "https://example.org/data.json"))) as fetch:
            result = await collect_benchmark_source(self.store, self.sid, "https://example.org/data.json", "download.json", "Fixture source")
            self.assertFalse(result["metadata"]["executable"])
            self.assertEqual(len(result["metadata"]["sha256"]), 64)
            self.assertEqual(fetch.await_args.kwargs["max_bytes"], 5_000_000)
        with self.assertRaises(ValueError):
            await collect_benchmark_source(self.store, self.sid, "https://example.org/install.py", "install.py", "Fixture source")

    async def test_pass_rate_requires_boolean_and_numeric_score_rejects_nan(self):
        for metric, row in (("pass_rate", {"passed": "true"}), ("mean_score", {"score": float("nan")})):
            register_benchmark(self.store, self.sid, {**self.manifest, "metrics": {metric: "Official evaluator per-case score"}})
            self.fixed_rows([{**row, "case_id": "0", "method": "parity", "seed": 0, "status": "ok"}])
            plan = self.plan(metrics=[metric])
            with self.assertRaises(ValueError):
                await run_benchmark(self.store, self.sid, plan["plan_id"], True)


if __name__ == "__main__":
    unittest.main()
