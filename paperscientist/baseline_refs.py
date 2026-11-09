"""Explicit local exchange of aggregate, content-verified benchmark baselines."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import uuid
from tempfile import NamedTemporaryFile

from . import benchmarks
from .research_routes import (
    _fingerprint,
    _measurements,
    compare_measurements,
    route_members,
    route_measurements,
)
from .store import dumps, now

EXPORT = "benchmark_baseline_export"
REFERENCE = "benchmark_baseline_reference"


def _session(store, sid, user_id):
    session = store.get_session(sid)
    if not session or session["parent_id"] or session["user_id"] != user_id:
        raise KeyError("研究会话不存在")
    return session


def _save(store, session, kind, summary):
    raw = json.dumps(
        summary, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
    ).encode()
    sha = hashlib.sha256(raw).hexdigest()
    sid = session["id"]
    folder = "exports" if kind == EXPORT else "references"
    rel = f"benchmarks/baselines/{folder}/{sha}.json"
    path = store.file(sid, rel)
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        live = db.execute(
            "SELECT id FROM sessions WHERE id=? AND user_id=? AND project_id=? AND parent_id IS NULL",
            (sid, session["user_id"], session["project_id"]),
        ).fetchone()
        flags = db.execute(
            "SELECT state FROM navigation WHERE user_id=? AND ((kind='session' AND target=?) OR (kind='project' AND target=?))",
            (session["user_id"], sid, session["project_id"]),
        ).fetchall()
        if not live or any(json.loads(r[0]).get("archived") for r in flags):
            raise ValueError("请在可写的研究会话中登记基线")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.stat().st_size != len(raw) or path.read_bytes() != raw:
                raise ValueError("已有基线文件内容冲突，请检查工作区")
        else:
            with NamedTemporaryFile(dir=path.parent, delete=False) as temp:
                tmp_path = Path(temp.name)
                try:
                    temp.write(raw)
                    temp.close()
                    os.link(tmp_path, path)
                finally:
                    tmp_path.unlink(missing_ok=True)
        row = db.execute(
            "SELECT id FROM artifacts WHERE session_id=? AND path=? AND kind=? AND json_extract(metadata,'$.sha256')=?",
            (sid, str(path), kind, sha),
        ).fetchone()
        artifact_id = row[0] if row else uuid.uuid4().hex
        if not row:
            db.execute(
                "INSERT INTO artifacts VALUES(?,?,?,?,?,?)",
                (
                    artifact_id,
                    sid,
                    str(path),
                    kind,
                    dumps({"sha256": sha, "origin_run_id": summary["run_id"]}),
                    now(),
                ),
            )
    return {
        "source_session_id": summary["source_session_id"],
        "artifact_id": artifact_id,
        "path": rel,
        "sha256": sha,
        "summary": summary,
    }


def _snapshot(store, source, plan_id, run_id):
    for sid in route_members(store, source["id"]):
        scores, ok = _measurements(store, sid, selected=(plan_id, run_id))
        if ok and scores:
            break
    else:
        raise ValueError("导出需要通过核验、完整且未被替代的基准运行")
    plan = benchmarks._plan(store, sid, plan_id)
    manifest = benchmarks._verified_record(
        store, sid, plan["manifest_path"], "benchmark_manifest"
    )
    receipt = benchmarks._verified_record(
        store, sid, f"runs/{run_id}.json", "execution"
    )
    cells = [
        {
            "match": list(key),
            "method": key[2],
            "metric": key[3],
            "grading": "frozen_targets"
            if key[-1] == "frozen-target-grader"
            else "pinned_adapter",
            "value": score["value"],
            "planned_rows": score["planned_rows"],
        }
        for key, score in sorted(scores.items())
    ]
    return {
        "schema": 1,
        "source_session_id": source["id"],
        **({"evaluator_session_id": sid} if sid != source["id"] else {}),
        "source_project_id": source["project_id"],
        "benchmark_id": plan["benchmark_id"],
        "plan_id": plan_id,
        "run_id": run_id,
        "protocol_sha256": benchmarks._hash(
            store.file(sid, f"benchmarks/plans/{plan_id}.json")
        ),
        "execution_sha256": benchmarks._hash(store.file(sid, f"runs/{run_id}.json")),
        "result_sha256": receipt["output_files"][
            benchmarks.execution_path(receipt, plan["result_path"])
        ],
        "dataset_sha256": plan["dataset_sha256"],
        "dataset_version": manifest["version"],
        "scope": plan["scope"],
        "provenance": manifest["provenance"],
        "split": plan["split"],
        "case_ids_sha256": _fingerprint(sorted(plan["case_ids"])),
        "seeds_sha256": _fingerprint(sorted(plan["seeds"])),
        "evaluator_script_sha256": plan["script_sha256"],
        "case_count": len(plan["case_ids"]),
        "seed_count": len(plan["seeds"]),
        "cells": cells,
    }


def export_baseline(store, session, plan_id, run_id):
    _session(store, session["id"], session["user_id"])
    return _save(store, session, EXPORT, _snapshot(store, session, plan_id, run_id))


def _read(store, sid, artifact_id, kind):
    with store.connect() as db:
        row = db.execute(
            "SELECT path,metadata FROM artifacts WHERE id=? AND session_id=? AND kind=?",
            (artifact_id, sid, kind),
        ).fetchone()
    if not row:
        raise KeyError("会话中没有这份基线摘要")
    relative = Path(row["path"]).relative_to(store.workspace(sid))
    path = store.file(sid, relative)
    if not path.is_file() or path.stat().st_size > benchmarks.MAX_BYTES:
        raise ValueError("基线摘要文件不可读取")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != json.loads(row["metadata"])["sha256"]:
        raise ValueError("基线摘要指纹发生变化")
    return json.loads(raw)


def attach_baseline(store, session, source_session_id, artifact_id):
    _session(store, session["id"], session["user_id"])
    source = _session(store, source_session_id, session["user_id"])
    if source["id"] == session["id"]:
        raise ValueError("请选择其他研究会话已导出的基线")
    summary = _read(store, source["id"], artifact_id, EXPORT)
    if _snapshot(store, source, summary["plan_id"], summary["run_id"]) != summary:
        raise ValueError("源会话中的基线回执或协议已变更")
    return _save(store, session, REFERENCE, summary)


def compare_reference(store, session, artifact_id):
    _session(store, session["id"], session["user_id"])
    summary = _read(store, session["id"], artifact_id, REFERENCE)
    base = {
        tuple(c["match"]): {
            **c,
            "run_id": summary["run_id"],
            "plan_id": summary["plan_id"],
        }
        for c in summary["cells"]
    }
    candidate, ok = route_measurements(store, session["id"])
    return {
        "reference_artifact_id": artifact_id,
        **compare_measurements(base, candidate, ok),
    }


def list_baselines(store, session):
    sid = session["id"]
    _session(store, sid, session["user_id"])
    runs = []
    for member in route_members(store, sid):
        audit = benchmarks.audit_benchmarks(store, member)
        runs.extend(
            {
                "plan_id": r["plan_id"],
                "run_id": r["run_id"],
                "scope": r["scope"],
                "provenance": r["provenance"],
                "evaluator_session_id": member,
            }
            for r in audit["results"]
            if audit["integrity_valid"]
            and r.get("valid")
            and r["protocol_complete"]
            and not r["superseded_by"]
        )
    refs = []
    for a in store.artifacts(sid):
        if a["kind"] == REFERENCE:
            try:
                summary = _read(store, sid, a["id"], REFERENCE)
                refs.append(
                    {
                        "artifact_id": a["id"],
                        "valid": True,
                        **{
                            k: summary[k]
                            for k in (
                                "source_project_id",
                                "benchmark_id",
                                "run_id",
                                "scope",
                                "provenance",
                                "case_count",
                                "seed_count",
                            )
                        },
                    }
                )
            except (ValueError, OSError, KeyError):
                refs.append({"artifact_id": a["id"], "valid": False})
    return {"runs": runs, "attached": refs}
