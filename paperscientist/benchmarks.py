"""Pre-registered, hash-bound benchmark protocols and local evaluator adapters.

This verifies execution, coverage and arithmetic, not the scientific validity of a
user-provided evaluator. Official suites must still use their official grader.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from .artifacts import run_python
from .network import fetch_public
from .store import identifier, now


CATALOG = (
    {"id": "scienceagentbench", "title": "ScienceAgentBench", "source_url": "https://github.com/OSU-NLP-Group/ScienceAgentBench",
     "paper_url": "https://arxiv.org/abs/2410.05080", "task": "Data-driven scientific program generation and official task-level execution evaluation",
     "keywords": ["scientific agent", "science agent", "research agent", "scientific discovery", "科研agent", "科研 agent", "科学发现", "科研智能体"],
     "requirements": "Pin the verified dataset split and matching artifacts; preserve the official rubric. Review dataset redistribution restrictions and per-task environments.",
     "not_evidence_for": "General research novelty, manuscript quality, or crash recovery correctness"},
    {"id": "mlagentbench", "title": "MLAgentBench", "source_url": "https://github.com/snap-stanford/MLAgentBench",
     "paper_url": "https://arxiv.org/abs/2310.03302", "task": "End-to-end ML experimentation from a dataset and an improvement objective",
     "keywords": ["machine learning", "ml agent", "ml experiment", "ml engineering", "机器学习", "模型训练", "自动实验", "科研agent", "科研 agent"],
     "requirements": "Pin task data and repository revision; use the official evaluator and matching baselines. Some tasks require Kaggle consent and substantial compute.",
     "not_evidence_for": "Universal scientific reasoning or failure recovery guarantees"},
    {"id": "mle-bench", "title": "MLE-bench", "source_url": "https://github.com/openai/mle-bench",
     "paper_url": "https://arxiv.org/abs/2410.07095", "task": "ML engineering on Kaggle competitions with competition-specific grading",
     "keywords": ["machine learning", "ml engineering", "kaggle", "机器学习", "模型训练", "机器学习工程"],
     "requirements": "Record competition rules, consent, split, grader revision, medal thresholds, hardware and budget. Never pool incompatible raw competition scores.",
     "not_evidence_for": "Scientific paper quality or an arbitrary local toy task"},
    {"id": "swe-bench", "title": "SWE-bench", "source_url": "https://github.com/SWE-bench/SWE-bench",
     "paper_url": "https://arxiv.org/abs/2310.06770", "task": "Repository issue resolution through patches evaluated by repository tests",
     "keywords": ["software agent", "coding agent", "code agent", "issue resolution", "program repair", "代码agent", "代码 agent", "软件智能体", "软件修复", "代码修复"],
     "requirements": "Pin dataset variant, instance IDs, container/grader revision and patch predictions. Official evaluation requires Docker; include build errors and unresolved tasks.",
     "not_evidence_for": "End-to-end science ability or arbitrary unit-test pass counts"},
)
METRICS = {"accuracy", "exact_match", "pass_rate", "mae", "rmse", "mean_score"}
MAX_BYTES = 20_000_000


def _hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("Benchmark file is missing or exceeds 20 MB")
    return json.loads(path.read_text(encoding="utf-8"))


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _https(value):
    parsed = urlparse(_text(value, "source URL"))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Primary sources must use HTTPS without embedded credentials")
    return value


def _save(store, sid, path, payload, kind):
    target = store.file(sid, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ValueError("Benchmark records are append-only; create a new version")
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    artifact = store.artifact(sid, target, kind, {"benchmark_id": payload.get("benchmark_id", payload.get("id")), "plan_id": payload.get("plan_id")})
    return {**payload, "path": path, "sha256": _hash(target), "artifact": artifact}


def _verified_record(store, sid, path, kind):
    target = store.file(sid, path)
    digest = _hash(target) if target.is_file() else ""
    matches = [a for a in store.artifacts(sid) if a["kind"] == kind and Path(a["path"]).resolve() == target.resolve() and a["metadata"].get("sha256") == digest]
    if not matches:
        raise ValueError(f"Missing or modified registered {kind}: {path}")
    return _json(target)


def discover_benchmarks(query: str, store=None, sid=None, limit=6):
    """Search the curated candidate registry; zero matches is not proof none exist."""
    query = _text(query, "research query")
    lowered = query.casefold()
    candidates = []
    for entry in CATALOG:
        matched = [word for word in entry["keywords"] if word.casefold() in lowered]
        if matched or entry["id"] in lowered:
            candidates.append({**entry, "matched_terms": matched, "status": "candidate_requires_applicability_review",
                               "version": "must_pin", "license": "must_check_code_and_dataset_separately"})
    if store is not None and sid is not None:
        registered = {}
        for artifact in store.artifacts(sid):
            if artifact["kind"] != "benchmark_manifest":
                continue
            path = str(Path(artifact["path"]).relative_to(store.workspace(sid))).replace("\\", "/")
            try:
                entry = _verified_record(store, sid, path, "benchmark_manifest")
            except (ValueError, OSError):
                continue
            matched = [word for word in [entry["id"], entry["title"], *entry.get("keywords", [])] if word.casefold() in lowered]
            if matched:
                registered[entry["id"]] = {**entry, "manifest_path": path, "matched_terms": matched,
                                           "status": "registered_requires_task_applicability_review"}
        candidates = [entry for entry in candidates if entry["id"] not in registered] + list(registered.values())
    candidates.sort(key=lambda x: len(x["matched_terms"]), reverse=True)
    result = {"query": query, "created_at": now(), "candidates": candidates[:max(1, min(int(limit), 20))],
              "decision": "review_candidates" if candidates else "search_primary_sources_for_domain_benchmarks",
              "instruction": "Select only if task, inputs, outputs, evaluation unit and target claim match. Otherwise persist a justified not_applicable decision. Synthetic recovery tests are complementary engineering evidence, not external benchmark scores."}
    if store is not None and sid is not None:
        return _save(store, sid, f"benchmarks/discovery/{uuid.uuid4().hex}.json", result, "benchmark_discovery")
    return result


def register_benchmark(store, sid, manifest: dict):
    """Register an extensible benchmark descriptor; no remote code is executed."""
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be an object")
    manifest = dict(manifest)
    manifest["id"] = identifier(manifest.get("id", ""))
    for field in ("title", "version", "task", "license", "license_notes"):
        manifest[field] = _text(manifest.get(field), field)
    if manifest["version"].casefold() in {"latest", "main", "master", "unknown", "must_pin"}:
        raise ValueError("Pin a release, dataset revision or immutable content hash")
    manifest["source_url"] = _https(manifest.get("source_url"))
    manifest["license_url"] = _https(manifest.get("license_url"))
    if "keywords" in manifest and (not isinstance(manifest["keywords"], list) or not all(isinstance(k, str) and k.strip() for k in manifest["keywords"])):
        raise ValueError("keywords must be nonempty strings")
    if manifest.get("provenance") not in {"external", "local_synthetic"}:
        raise ValueError("provenance must be external or local_synthetic")
    if not isinstance(manifest.get("splits"), list) or not manifest["splits"] or not all(isinstance(x, str) and x for x in manifest["splits"]):
        raise ValueError("Declare the available dataset splits")
    if not isinstance(manifest.get("metrics"), dict) or not manifest["metrics"] or set(manifest["metrics"]) - METRICS:
        raise ValueError(f"metrics must map supported metric names to definitions: {sorted(METRICS)}")
    for metric, definition in manifest["metrics"].items():
        _text(definition, f"{metric} definition")
    manifest.update(schema_version=1, created_at=now())
    return _save(store, sid, f"benchmarks/registry/{manifest['id']}/{uuid.uuid4().hex}.json", manifest, "benchmark_manifest")


async def collect_benchmark_source(store, sid, url: str, path: str, license_note: str, max_bytes=5_000_000):
    """Bounded source/data collection only, never installs or executes a download."""
    _https(url)
    _text(license_note, "license_note")
    if Path(path).suffix.lower() not in {".json", ".jsonl", ".csv", ".tsv", ".txt", ".md", ".pdf"}:
        raise ValueError("Only source documents and data formats may be collected")
    target = store.file(sid, path)
    if target.exists():
        raise ValueError("Choose a new source path; existing evidence is not overwritten")
    data, mime, final_url = await fetch_public(url, max_bytes=max(1, min(int(max_bytes), MAX_BYTES)))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return store.artifact(sid, target, "benchmark_source", {"source_url": url, "resolved_url": final_url,
                          "license_note": license_note, "content_type": mime, "collected_at": now(), "executable": False})


def _manifest(store, sid, benchmark_id, path=None):
    identifier(benchmark_id)
    if path:
        result = _verified_record(store, sid, path, "benchmark_manifest")
        if result["id"] != benchmark_id:
            raise ValueError("Manifest benchmark ID mismatch")
        return result, path
    entries = [a for a in store.artifacts(sid) if a["kind"] == "benchmark_manifest" and a["metadata"].get("benchmark_id") == benchmark_id]
    if not entries:
        raise ValueError("Register a versioned benchmark manifest first")
    chosen = max(entries, key=lambda a: a.get("created_at", ""))
    path = str(Path(chosen["path"]).relative_to(store.workspace(sid))).replace("\\", "/")
    return _verified_record(store, sid, path, "benchmark_manifest"), path


def _dataset(store, sid, path):
    cases = _json(store.file(sid, path))
    if not isinstance(cases, list) or not cases or len(cases) > 100_000:
        raise ValueError("Dataset index must contain 1–100000 case objects")
    result = {}
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Dataset index cases must be objects")
        cid = _text(case.get("case_id"), "case_id")
        _text(case.get("split"), "split")
        if cid in result:
            raise ValueError(f"Duplicate dataset case ID: {cid}")
        result[cid] = case
    return result


def plan_benchmark(store, sid, benchmark_id: str, protocol: dict | None = None, protocol_path: str = ""):
    """Freeze applicability and a local protocol before running any evaluation."""
    if protocol_path:
        if protocol is not None:
            raise ValueError("Provide protocol or protocol_path, not both")
        source = store.file(sid, protocol_path)
        protocol_path = str(source.relative_to(store.workspace(sid))).replace("\\", "/")
        protocol = _json(source)
    if not isinstance(protocol, dict):
        raise ValueError("protocol must be an object")
    manifest, manifest_path = _manifest(store, sid, benchmark_id, protocol.get("manifest_path"))
    plan = dict(protocol)
    if protocol_path:
        paths = plan.get("input_paths", [])
        if not isinstance(paths, list):
            raise ValueError("input_paths must be a list")
        plan["input_paths"] = [*paths, protocol_path] if protocol_path not in paths else list(paths)
        plan["protocol_source_path"] = protocol_path
    plan.update(plan_id=f"bench_{uuid.uuid4().hex}", benchmark_id=benchmark_id, manifest_path=manifest_path,
                manifest_sha256=_hash(store.file(sid, manifest_path)), created_at=now(), created_ns=time.time_ns())
    for field in ("rationale", "claim", "task_match"):
        plan[field] = _text(plan.get(field), field)
    if plan.get("decision") == "not_applicable":
        if plan.get("supersedes"):
            raise ValueError("A selected protocol can only be superseded by another selected protocol")
        return _save(store, sid, f"benchmarks/plans/{plan['plan_id']}.json", plan, "benchmark_protocol")
    if plan.get("decision") != "selected":
        raise ValueError("decision must be selected or not_applicable")
    if plan.get("scope") not in {"smoke", "subset", "full_split"}:
        raise ValueError("scope must be smoke, subset or full_split")
    if manifest["provenance"] == "local_synthetic" and plan["scope"] != "smoke":
        raise ValueError("Synthetic adapter checks must use smoke scope")
    if plan.get("split") not in manifest["splits"]:
        raise ValueError("Protocol split is not declared in the manifest")
    if plan.get("adapter") != "local_python":
        raise ValueError("Only the configured local_python adapter is supported; no remote code auto-run")
    plan["evaluator_description"] = _text(plan.get("evaluator_description"), "evaluator_description")
    plan["limitations"] = _text(plan.get("limitations"), "limitations")
    for field in ("script_path", "dataset_path", "result_path"):
        plan[field] = str(store.file(sid, _text(plan.get(field), field)).relative_to(store.workspace(sid))).replace("\\", "/")
    if Path(plan["script_path"]).suffix != ".py" or Path(plan["result_path"]).suffix != ".json":
        raise ValueError("Adapter script must be Python and results must be JSON")
    if len({plan["script_path"], plan["dataset_path"], plan["result_path"]}) != 3:
        raise ValueError("Script, dataset and result paths must be distinct")
    cases = _dataset(store, sid, plan["dataset_path"])
    ids = plan.get("case_ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(c, str) for c in ids) or len(ids) != len(set(ids)):
        raise ValueError("case_ids must be nonempty and unique")
    if any(c not in cases or cases[c]["split"] != plan["split"] for c in ids):
        raise ValueError("Selected cases must exist in the frozen dataset split")
    all_ids = {c for c, row in cases.items() if row["split"] == plan["split"]}
    if plan["scope"] == "full_split" and set(ids) != all_ids:
        raise ValueError("full_split requires every case in the supplied split index")
    for name in ("methods", "seeds", "metrics"):
        values = plan.get(name)
        if not isinstance(values, list) or not values or not all(type(v) in {int, str} for v in values) or len(values) != len(set(values)):
            raise ValueError(f"{name} must be nonempty and unique")
    if not all(isinstance(m, str) and m.strip() for m in plan["methods"]):
        raise ValueError("methods must name the evaluated agents/baselines")
    if not all(type(s) is int for s in plan["seeds"]):
        raise ValueError("seeds must be integers")
    if set(plan["metrics"]) - set(manifest["metrics"]):
        raise ValueError("Protocol metrics must be defined by the manifest")
    budget = plan.get("budget", {})
    if type(budget.get("timeout_seconds")) is not int or not 1 <= budget["timeout_seconds"] <= 300:
        raise ValueError("budget.timeout_seconds must be 1–300 (enforced by the local runner)")
    expected = len(ids) * len(plan["methods"]) * len(plan["seeds"])
    if type(budget.get("max_evaluations")) is not int or not expected <= budget["max_evaluations"] <= 100_000:
        raise ValueError("budget.max_evaluations must cover the protocol and be <=100000")
    _text(budget.get("hardware"), "budget.hardware")
    input_paths = plan.get("input_paths", [])
    if not isinstance(input_paths, list) or len(input_paths) > 256 or not all(isinstance(p, str) for p in input_paths):
        raise ValueError("input_paths must list at most 256 local source/data/evaluator dependency files")
    plan["input_sha256"] = {}
    for path in input_paths:
        target = store.file(sid, path)
        normalized = str(target.relative_to(store.workspace(sid))).replace("\\", "/")
        if normalized == plan["result_path"]:
            raise ValueError("An output cannot also be a frozen input")
        plan["input_sha256"][normalized] = _hash(target)
    plan.update(script_sha256=_hash(store.file(sid, plan["script_path"])), dataset_sha256=_hash(store.file(sid, plan["dataset_path"])),
                expected_evaluations=expected, split_index_cases=len(all_ids),
                budget_enforcement={"timeout_seconds": "process-tree timeout", "max_evaluations": "protocol and coverage validation", "hardware": "declared, not a resource quota"})
    _validate_revision(store, sid, plan)
    return _save(store, sid, f"benchmarks/plans/{plan['plan_id']}.json", plan, "benchmark_protocol")


def _validate_revision(store, sid, plan):
    """A correction adds a receipt; it cannot erase failures or reduce coverage."""
    parents = plan.get("supersedes", [])
    if not isinstance(parents, list) or not all(isinstance(p, str) for p in parents) or len(parents) != len(set(parents)):
        raise ValueError("supersedes must be a list of unique existing plan IDs")
    if not parents:
        return
    if plan.get("decision") != "selected":
        raise ValueError("Only a selected protocol may supersede earlier plans")
    _text(plan.get("revision_reason"), "revision_reason")
    _text(plan.get("prior_exposure"), "prior_exposure")
    for pid in parents:
        old = _verified_record(store, sid, f"benchmarks/plans/{identifier(pid)}.json", "benchmark_protocol")
        if old["decision"] != "selected" or old["benchmark_id"] != plan["benchmark_id"]:
            raise ValueError("Revisions must replace selected protocols for the same benchmark")
        if old["created_ns"] >= plan["created_ns"]:
            raise ValueError("Revisions must follow their predecessors")
        for field in ("split", "manifest_sha256", "dataset_sha256"):
            if old[field] != plan[field]:
                raise ValueError(f"Revision cannot change {field}; register a separate evaluation")
        for field in ("case_ids", "methods", "seeds", "metrics"):
            if not set(old[field]).issubset(plan[field]):
                raise ValueError(f"Revision cannot drop {field}")
        if old["scope"] == "full_split" and plan["scope"] != "full_split":
            raise ValueError("Revision cannot reduce full_split scope")


def protect_benchmark_file(store, sid, path):
    """Guard ordinary file tools; Python remains trusted execution, audited by hashes.

    Historical inputs stay protected too. Repairs must use new paths, so a
    revision never silently changes the meaning of an earlier run.
    """
    target = store.file(sid, path)
    for artifact in store.artifacts(sid):
        if not artifact["kind"].startswith("benchmark_"):
            continue
        record_path = Path(artifact["path"])
        if target == record_path.resolve():
            raise PermissionError("Registered benchmark evidence is append-only; use a new path")
        if artifact["kind"] != "benchmark_protocol":
            continue
        rel = str(record_path.relative_to(store.workspace(sid)))
        plan = _verified_record(store, sid, rel, "benchmark_protocol")
        if plan["decision"] != "selected":
            continue
        inputs = [plan["script_path"], plan["dataset_path"], plan["manifest_path"], *plan.get("input_sha256", {})]
        if target in {store.file(sid, p) for p in inputs}:
            raise PermissionError("Frozen benchmark input is immutable; copy to a new path and register a revision with supersedes, revision_reason and prior_exposure")


def _plan(store, sid, plan_id):
    identifier(plan_id)
    plan = _verified_record(store, sid, f"benchmarks/plans/{plan_id}.json", "benchmark_protocol")
    if plan["decision"] != "selected":
        raise ValueError("Benchmark protocol is not selected")
    for path_key, hash_key in (("manifest_path", "manifest_sha256"), ("script_path", "script_sha256"), ("dataset_path", "dataset_sha256")):
        if _hash(store.file(sid, plan[path_key])) != plan[hash_key]:
            raise ValueError(f"Frozen benchmark input changed: {path_key}; register a new protocol")
    for path, digest in plan.get("input_sha256", {}).items():
        if _hash(store.file(sid, path)) != digest:
            raise ValueError(f"Frozen benchmark input changed: {path}; register a new protocol")
    return plan


def _execution(store, sid, plan, result_path, run_id, result_digest=None):
    identifier(run_id)
    run = _verified_record(store, sid, f"runs/{run_id}.json", "execution")
    if run.get("run_id") != run_id or run.get("exit_code") != 0 or run.get("timed_out"):
        raise ValueError("Evaluation requires a successful non-timeout execution")
    if run.get("script") != plan["script_path"] or run.get("script_sha256") != plan["script_sha256"]:
        raise ValueError("Execution did not use the frozen evaluator script")
    # Existing runner IDs encode start time, preventing post-hoc protocol creation.
    if not re.fullmatch(r"run_\d+", run_id) or int(run_id[4:]) <= plan["created_ns"]:
        raise ValueError("Benchmark protocol must precede execution")
    if run.get("duration_seconds", math.inf) > plan["budget"]["timeout_seconds"] + 2:
        raise ValueError("Recorded execution exceeded the protocol time budget")
    if run.get("output_files", {}).get(result_path) != (result_digest or _hash(store.file(sid, result_path))):
        raise ValueError("Result was not produced by this execution or its hash changed")
    return run


def _number(value, label):
    if type(value) not in {float, int} or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _evaluate(store, sid, plan, result_path):
    rows = _json(store.file(sid, result_path))
    if not isinstance(rows, list):
        raise ValueError("Results must be a list of per-case evaluation rows")
    expected = set(itertools.product(plan["case_ids"], plan["methods"], plan["seeds"]))
    cases = _dataset(store, sid, plan["dataset_path"])
    seen, values, failed = set(), {}, []
    for row in rows:
        if not isinstance(row, dict) or type(row.get("seed")) is not int:
            raise ValueError("Each result must contain a case ID, method and integer seed")
        key = (row.get("case_id"), row.get("method"), row["seed"])
        if key not in expected or key in seen:
            raise ValueError(f"Unexpected or duplicate evaluation: {key}")
        seen.add(key)
        if row.get("status") not in {"ok", "error", "timeout"}:
            raise ValueError("Result status must be ok, error or timeout")
        if row["status"] != "ok":
            failed.append({"case_id": key[0], "method": key[1], "seed": key[2], "status": row["status"]})
        for metric in plan["metrics"]:
            bucket = values.setdefault((key[1], metric), [])
            if row["status"] != "ok":
                if metric in {"pass_rate", "accuracy", "exact_match"}:
                    bucket.append(0.0)
                continue
            target = cases[key[0]].get("target")
            if metric == "pass_rate":
                if type(row.get("passed")) is not bool:
                    raise ValueError("pass_rate requires the evaluator's boolean passed field")
                value = float(row["passed"])
            elif metric in {"accuracy", "exact_match"}:
                if "target" not in cases[key[0]] or "prediction" not in row:
                    raise ValueError("Prediction metrics require frozen dataset targets and predictions")
                value = float(type(row["prediction"]) is type(target) and row["prediction"] == target)
            elif metric in {"mae", "rmse"}:
                error = _number(row.get("prediction"), "prediction") - _number(target, "frozen target")
                value = abs(error) if metric == "mae" else error * error
            else:
                value = _number(row.get("score"), "official evaluator score")
            if not math.isfinite(value):
                raise ValueError("Metric calculation overflowed; use a numerically stable official evaluator")
            bucket.append(value)
    missing = sorted(expected - seen)
    denominator = len(plan["case_ids"]) * len(plan["seeds"])
    scores = {}
    for method in plan["methods"]:
        scores[method] = {}
        for metric in plan["metrics"]:
            series = values.get((method, metric), [])
            divisor = denominator if metric in {"pass_rate", "accuracy", "exact_match"} else len(series)
            value = math.fsum(item / divisor for item in series) if divisor else None
            if metric == "rmse" and value is not None:
                value = math.sqrt(value)
            scores[method][metric] = {"value": value, "scored_rows": len(series), "planned_rows": denominator,
                                      "missing_and_errors_as_zero": metric in {"pass_rate", "accuracy", "exact_match"}}
    return {"expected": len(expected), "observed": len(seen), "coverage": len(seen) / len(expected),
            "missing": [dict(zip(("case_id", "method", "seed"), key)) for key in missing], "failed": failed,
            "scores": scores, "protocol_complete": not missing and not failed,
            "official_benchmark_complete": False,
            "interpretation": "Verified local execution and selected protocol coverage only. Official comparability requires the pinned official grader, dataset inventory, rules and budget; this audit does not certify them."}


def record_benchmark_result(store, sid, plan_id: str, result_path: str, run_id: str):
    plan = _plan(store, sid, plan_id)
    result_path = str(store.file(sid, result_path).relative_to(store.workspace(sid))).replace("\\", "/")
    if result_path != plan["result_path"]:
        raise ValueError("Result path differs from the frozen protocol")
    _execution(store, sid, plan, result_path, run_id)
    summary = _evaluate(store, sid, plan, result_path)
    manifest = _verified_record(store, sid, plan["manifest_path"], "benchmark_manifest")
    result_id = uuid.uuid4().hex
    snapshot_path = f"benchmarks/results/{plan_id}/{result_id}.data.json"
    snapshot = store.file(sid, snapshot_path)
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_bytes(store.file(sid, result_path).read_bytes())
    store.artifact(sid, snapshot, "benchmark_result_data", {"plan_id": plan_id, "run_id": run_id})
    record = {"benchmark_id": plan["benchmark_id"], "plan_id": plan_id, "created_at": now(), "run_id": run_id,
              "result_path": result_path, "result_sha256": _hash(store.file(sid, result_path)),
              "result_snapshot_path": snapshot_path,
              "scope": plan["scope"], "provenance": manifest["provenance"], "summary": summary}
    return _save(store, sid, f"benchmarks/results/{plan_id}/{result_id}.json", record, "benchmark_result")


async def run_benchmark(store, sid, plan_id: str, enabled: bool):
    plan = _plan(store, sid, plan_id)
    if not enabled:
        raise PermissionError("Local execution must be enabled to run a benchmark")
    run = await run_python(store, sid, plan["script_path"], enabled=True, timeout=plan["budget"]["timeout_seconds"])
    attempt = _save(store, sid, f"benchmarks/attempts/{plan_id}/{run['run_id']}.json", {
        "plan_id": plan_id, "benchmark_id": plan["benchmark_id"], "run_id": run["run_id"], "created_at": now(),
        "exit_code": run.get("exit_code"), "timed_out": bool(run.get("timed_out")),
        "duration_seconds": run.get("duration_seconds"),
    }, "benchmark_attempt")
    if run.get("exit_code") != 0 or run.get("timed_out"):
        return {"plan_id": plan_id, "status": "execution_failed", "execution": run, "attempt": attempt, "protocol_complete": False}
    return record_benchmark_result(store, sid, plan_id, plan["result_path"], run["run_id"])


def audit_benchmarks(store, sid):
    """Re-check current files against durable execution/manifest/protocol receipts."""
    results, decisions, pending, attempts = [], [], [], []
    artifacts = store.artifacts(sid)
    recorded_plans = set()
    plans, superseded_by = {}, {}
    for artifact in artifacts:
        if artifact["kind"] != "benchmark_protocol":
            continue
        path = str(Path(artifact["path"]).relative_to(store.workspace(sid)))
        try:
            plan = _verified_record(store, sid, path, "benchmark_protocol")
            _validate_revision(store, sid, plan)
            plans[plan["plan_id"]] = plan
            for parent in plan.get("supersedes", []):
                superseded_by.setdefault(parent, []).append(plan["plan_id"])
        except (ValueError, KeyError, TypeError, OSError) as exc:
            results.append({"path": path, "valid": False, "protocol_complete": False, "error": str(exc)})
    for artifact in artifacts:
        if artifact["kind"] != "benchmark_attempt":
            continue
        path = str(Path(artifact["path"]).relative_to(store.workspace(sid))).replace("\\", "/")
        try:
            attempt = _verified_record(store, sid, path, "benchmark_attempt")
            run = _verified_record(store, sid, f"runs/{identifier(attempt['run_id'])}.json", "execution")
            attempts.append({"plan_id": attempt["plan_id"], "run_id": run["run_id"], "exit_code": run["exit_code"],
                             "timed_out": run["timed_out"], "duration_seconds": run["duration_seconds"], "valid": True})
        except (ValueError, KeyError, TypeError, OSError) as exc:
            attempts.append({"path": path, "valid": False, "error": str(exc)})
    for artifact in artifacts:
        if artifact["kind"] != "benchmark_result":
            continue
        path = str(Path(artifact["path"]).relative_to(store.workspace(sid))).replace("\\", "/")
        try:
            record = _verified_record(store, sid, path, "benchmark_result")
            recorded_plans.add(record["plan_id"])
            # Verify durable records even for superseded plans. Supersession may
            # explain a changed input, never a modified receipt or result.
            plan = _verified_record(store, sid, f"benchmarks/plans/{identifier(record['plan_id'])}.json", "benchmark_protocol")
            snapshot_path = record["result_snapshot_path"]
            _verified_record(store, sid, snapshot_path, "benchmark_result_data")
            if _hash(store.file(sid, snapshot_path)) != record["result_sha256"]:
                raise ValueError("Recorded result hash changed")
            _execution(store, sid, plan, record["result_path"], record["run_id"], record["result_sha256"])
            try:
                _plan(store, sid, record["plan_id"])
            except (ValueError, OSError) as exc:
                if record["plan_id"] not in superseded_by:
                    raise
                results.append({"plan_id": record["plan_id"], "run_id": record["run_id"],
                                "valid": False, "protocol_complete": False, "historical_input_failure": True,
                                "error": str(exc)})
                continue
            summary = _evaluate(store, sid, plan, snapshot_path)
            results.append({"plan_id": record["plan_id"], "run_id": record["run_id"], "scope": record["scope"],
                            "provenance": record["provenance"], "valid": True, **summary})
        except (ValueError, KeyError, TypeError, OSError) as exc:
            results.append({"path": path, "plan_id": artifact["metadata"].get("plan_id"),
                            "valid": False, "protocol_complete": False, "error": str(exc)})
    for plan in plans.values():
        if plan["decision"] == "not_applicable":
            decisions.append({"benchmark_id": plan["benchmark_id"], "decision": plan["decision"], "rationale": plan["rationale"]})
        elif plan["plan_id"] not in recorded_plans and plan["plan_id"] not in superseded_by:
            pending.append(plan["plan_id"])
    for record in results + attempts:
        record["superseded_by"] = superseded_by.get(record.get("plan_id"), [])
    latest = {result["plan_id"]: result for result in results if result.get("plan_id") and not result["superseded_by"]}
    historical_integrity_valid = all(record.get("valid") for record in [*results, *attempts])
    integrity_valid = all(record.get("valid") or (record.get("superseded_by") and record.get("historical_input_failure"))
                          for record in [*results, *attempts])
    return {"results": results, "attempts": attempts, "not_applicable": decisions, "pending_plans": pending,
            "integrity_valid": integrity_valid,
            "historical_integrity_valid": historical_integrity_valid,
            "superseded_protocols": [{"plan_id": pid, "superseded_by": children,
                                      "had_result": pid in recorded_plans} for pid, children in superseded_by.items()],
            "revisions": [{"plan_id": p["plan_id"], "supersedes": p["supersedes"],
                           "revision_reason": p["revision_reason"], "prior_exposure": p["prior_exposure"]}
                          for p in plans.values() if p.get("supersedes")],
            "all_selected_protocols_complete": bool(latest) and not pending and integrity_valid and all(r.get("protocol_complete") for r in latest.values()),
            "official_benchmark_complete": False}
