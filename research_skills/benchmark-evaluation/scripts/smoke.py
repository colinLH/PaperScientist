"""Run the real local adapter with explicitly synthetic parity cases.

This is a plumbing check, never a ScienceAgentBench/MLAgentBench result.
Optional source collection downloads only the official ScienceAgentBench README.
"""
import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from paperscientist.benchmarks import (  # noqa: E402
    audit_benchmarks, collect_benchmark_source, discover_benchmarks,
    plan_benchmark, register_benchmark, run_benchmark,
)
from paperscientist.store import Store  # noqa: E402


async def main(output, collect=False):
    store = Store(output)
    sid = f"benchmark-smoke-{uuid.uuid4().hex[:12]}"
    store.session(sid)
    discovery = discover_benchmarks("scientific agent machine learning experimentation", store, sid)
    source = None
    if collect:
        source = await collect_benchmark_source(
            store, sid, "https://raw.githubusercontent.com/OSU-NLP-Group/ScienceAgentBench/main/README.md",
            "scienceagentbench-source.md",
            "Public official documentation for applicability review only. No benchmark data or code installed; dataset redistribution restrictions still apply.")
    register_benchmark(store, sid, {
        "id": "synthetic-parity-smoke", "title": "Synthetic parity adapter smoke", "version": "fixture-v1",
        "source_url": "https://github.com/colinLH/PaperScientist",
        "license": "locally-authored-test-fixture", "license_url": "https://github.com/colinLH/PaperScientist",
        "license_notes": "Six locally authored parity inputs, not external scientific benchmark data.",
        "task": "Verify adapter execution, coverage and arithmetic", "provenance": "local_synthetic",
        "splits": ["test"], "metrics": {"accuracy": "Exact label match / planned evaluations"},
    })
    store.file(sid, "cases.json").write_text(json.dumps([
        {"case_id": str(i), "split": "test", "x": i, "target": i % 2} for i in range(6)
    ]), encoding="utf-8")
    store.file(sid, "evaluate.py").write_text('''import json
from pathlib import Path
cases = json.loads(Path("cases.json").read_text(encoding="utf-8"))
rows = []
for seed in [0, 1]:
    for method in ["parity", "always-one"]:
        for case in cases:
            prediction = case["x"] % 2 if method == "parity" else 1
            rows.append(dict(case_id=case["case_id"], method=method, seed=seed, status="ok", prediction=prediction))
Path("results.json").write_text(json.dumps(rows), encoding="utf-8")
''', encoding="utf-8")
    plan = plan_benchmark(store, sid, "synthetic-parity-smoke", {
        "decision": "selected", "rationale": "Verify local adapter operation and persisted provenance",
        "claim": "No scientific benchmark performance claim", "task_match": "Synthetic adapter plumbing check",
        "scope": "smoke", "split": "test", "case_ids": [str(i) for i in range(6)],
        "methods": ["parity", "always-one"], "seeds": [0, 1], "metrics": ["accuracy"],
        "adapter": "local_python", "script_path": "evaluate.py", "dataset_path": "cases.json", "result_path": "results.json",
        "evaluator_description": "Reviewed deterministic parity arithmetic script, local CPU",
        "limitations": "Six synthetic cases only; no external suite, model inference or scientific-agent score",
        "budget": {"timeout_seconds": 20, "max_evaluations": 24, "hardware": "local CPU"},
    })
    result = await run_benchmark(store, sid, plan["plan_id"], enabled=True)
    audit = audit_benchmarks(Store(output), sid)
    report = {"session_id": sid, "workspace": str(store.workspace(sid)), "discovery": discovery["path"],
              "source": source, "result": result, "audit_after_store_restart": audit}
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "smoke-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(report_path), "run_id": result["run_id"],
                      "expected": result["summary"]["expected"], "observed": result["summary"]["observed"],
                      "scores": result["summary"]["scores"], "restored_audit_passed": audit["all_selected_protocols_complete"],
                      "official_benchmark_complete": False}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".test-output/benchmark-harness"))
    parser.add_argument("--collect-primary-source", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.output.resolve(), args.collect_primary_source))
