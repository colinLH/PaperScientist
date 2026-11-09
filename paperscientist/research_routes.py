"""Research routes are the project's existing root conversations and their forks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import benchmarks
from .store import dumps, now

EMPTY_NOTE = {
    "reason": "",
    "status": "exploring",
    "outcome": "",
    "next_step": "",
    "revision": 0,
}


class RevisionConflict(ValueError):
    pass


def project_routes(actions, pid):
    actions.target("project", pid)
    project_archived = bool(actions.metadata("project", pid).get("archived"))
    with actions.store.connect() as db:
        sessions = db.execute(
            """SELECT s.id,s.title,n.state,
            (SELECT COUNT(*) FROM artifacts a WHERE a.session_id=s.id) AS artifact_count,
            (SELECT status FROM research_runs r WHERE r.session_id=s.id ORDER BY created_at DESC, id DESC LIMIT 1) AS run_status
            FROM sessions s LEFT JOIN navigation n ON n.user_id=s.user_id AND n.kind='session' AND n.target=s.id
            WHERE s.project_id=? AND s.user_id='local' AND s.parent_id IS NULL ORDER BY s.created_at,s.id""",
            (pid,),
        ).fetchall()
    visible = {s["id"] for s in sessions}
    result = []
    for s in sessions:
        nav = json.loads(s["state"] or "{}")
        parent = nav.get("forked_from")
        result.append(
            {
                "id": s["id"],
                "title": s["title"],
                "parent_id": parent if parent in visible else None,
                **EMPTY_NOTE,
                **nav.get("route", {}),
                "archived": project_archived or bool(nav.get("archived")),
                "run_status": s["run_status"],
                "artifact_count": s["artifact_count"],
            }
        )
    return {"project_id": pid, "routes": result}


def update_route(store, pid, sid, revision, note, user_id="local"):
    """Compare-and-swap only the route fields, preserving sidebar settings and fork origin."""
    if note.get("status") not in {"exploring", "supported", "rejected", "stopped"}:
        raise ValueError("未知路线状态")
    if any(
        not isinstance(note.get(key), str) or len(note[key]) > 1000
        for key in ("reason", "outcome", "next_step")
    ):
        raise ValueError("路线问题、结果与下一步每项最多 1000 字")
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            """SELECT s.id,n.state,p.state AS project_state FROM sessions s
            LEFT JOIN navigation n ON n.user_id=s.user_id AND n.kind='session' AND n.target=s.id
            LEFT JOIN navigation p ON p.user_id=s.user_id AND p.kind='project' AND p.target=s.project_id
            WHERE s.id=? AND s.user_id=? AND s.project_id=? AND s.parent_id IS NULL""",
            (sid, user_id, pid),
        ).fetchone()
        if not row:
            raise KeyError("项目中没有这条研究路线")
        state = json.loads(row["state"] or "{}")
        if state.get("archived") or json.loads(row["project_state"] or "{}").get(
            "archived"
        ):
            raise RevisionConflict("请先恢复归档的研究路线或项目")
        if state.get("route", {}).get("revision", 0) != revision:
            raise RevisionConflict("研究路线已在另一个窗口更新，请刷新后重试")
        state["route"] = {**note, "revision": revision + 1}
        db.execute(
            "INSERT OR REPLACE INTO navigation VALUES(?,'session',?,?)",
            (user_id, sid, dumps(state)),
        )
        db.execute(
            "INSERT INTO events(session_id,kind,data,created_at) VALUES(?,?,?,?)",
            (sid, "research_route", dumps(state["route"]), now()),
        )
    return state["route"]


def route_context(store, session):
    """Route notes are authored project data. Specialist and review contexts stay isolated."""
    if session.get("parent_id"):
        return {}
    with store.connect() as db:
        rows = db.execute(
            """SELECT s.id,s.title,n.state FROM navigation n JOIN sessions s
            ON n.target=s.id AND n.user_id=s.user_id WHERE n.kind='session' AND s.parent_id IS NULL
            AND s.user_id=? AND s.project_id=? AND (s.id=? OR
              json_extract(n.state,'$.route.status') IN ('rejected','stopped'))
            ORDER BY s.updated_at DESC,s.id""",
            (session["user_id"], session["project_id"], session["id"]),
        ).fetchall()
    context = {}
    for row in rows:
        state = json.loads(row["state"])
        note = state.get("route")
        if not note:
            continue
        if row["id"] == session["id"]:
            context["current"] = note
        elif note.get("outcome") and len(context.get("prior_decisions", [])) < 3:
            context.setdefault("prior_decisions", []).append(
                {
                    "session_id": row["id"],
                    "title": row["title"],
                    "status": note["status"],
                    "reason": note.get("reason", "")[:350],
                    "outcome": note["outcome"][:600],
                }
            )
    return context


def _registered_files(store, sid):
    """Compare latest registered versions, without treating live unregistered files as evidence."""
    root = store.workspace(sid)
    result = {}
    for entry in store.artifacts(sid):
        path = Path(entry["path"])
        if path.is_relative_to(root):
            result[path.relative_to(root).as_posix()] = entry["metadata"].get("sha256")
    return result


def _fingerprint(value):
    data = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(data).hexdigest()


def _measurements(store, sid, selected=None):
    audit = benchmarks.audit_benchmarks(store, sid)
    if not audit["integrity_valid"]:
        return {}, False
    latest = {
        r["plan_id"]: r
        for r in audit["results"]
        if r.get("valid")
        and not r["superseded_by"]
        and (selected is None or (r["plan_id"], r["run_id"]) == selected)
    }
    data = {}
    for plan_id, r in latest.items():
        if not r["protocol_complete"]:
            continue
        plan = benchmarks._plan(store, sid, plan_id)
        manifest = benchmarks._verified_record(
            store, sid, plan["manifest_path"], "benchmark_manifest"
        )
        # Prediction metrics are recomputed by the same local grader from the frozen targets.
        # Its prediction-producing adapter can change between research routes. Scores supplied by
        # external adapters also require the evaluator script and its auxiliary inputs to match.
        signature = _fingerprint(
            [
                plan["dataset_sha256"],
                plan["scope"],
                plan["split"],
                sorted(plan["case_ids"]),
                sorted(plan["seeds"]),
                manifest["version"],
                manifest["task"],
                manifest["source_url"],
                manifest["provenance"],
                sorted(plan["budget"].items()),
            ]
        )
        adapter_grader = None
        if {"pass_rate", "mean_score"}.intersection(plan["metrics"]):
            receipt = benchmarks.execution_receipt(store, sid, r["run_id"])
            sources = receipt.get("input_source_hashes", {})
            if receipt.get("execution_dir"):
                prefix = receipt["execution_dir"] + "/"
                sources = {
                    path.removeprefix(prefix): sha
                    for path, sha in sources.items()
                    if path.startswith(prefix)
                }
            if sources.get(plan["script_path"]) == plan["script_sha256"]:
                # The receipt includes local Python helpers present at execution time, including
                # helpers not named in the pre-registration. Only fingerprints leave the session.
                adapter_grader = _fingerprint(
                    [
                        sorted(sources.items()),
                        sorted(plan.get("input_sha256", {}).items()),
                        plan["evaluator_description"],
                    ]
                )
        for method, metrics in r["scores"].items():
            for metric, score in metrics.items():
                if (
                    score["value"] is None
                    or score["scored_rows"] != score["planned_rows"]
                ):
                    continue
                grader = (
                    adapter_grader
                    if metric in {"pass_rate", "mean_score"}
                    else "frozen-target-grader"
                )
                if grader is None:
                    continue
                key = (
                    plan["benchmark_id"],
                    signature,
                    method,
                    metric,
                    _fingerprint(manifest["metrics"][metric]),
                    grader,
                )
                old = data.get(key)
                if old and int(old["run_id"][4:]) > int(r["run_id"][4:]):
                    continue
                data[key] = {
                    **score,
                    "run_id": r["run_id"],
                    "plan_id": plan_id,
                    "scope": r["scope"],
                    "provenance": r["provenance"],
                }
    return data, True


def route_members(store, sid):
    """A route comprises its root and the same-project, non-blind specialists reporting to it."""
    session = store.get_session(sid)
    if not session or session["parent_id"]:
        raise KeyError("研究路线不存在")
    with store.connect() as db:
        children = db.execute(
            """SELECT s.id FROM sessions s JOIN agents a ON a.id=s.id AND a.parent_id=s.parent_id
               WHERE s.parent_id=? AND s.user_id=? AND s.project_id=?
               AND coalesce(json_extract(a.data,'$.isolated_review'),0)=0 ORDER BY s.id""",
            (sid, session["user_id"], session["project_id"]),
        ).fetchall()
    return [sid, *(row[0] for row in children)]


def route_measurements(store, sid):
    combined = {}
    for member in route_members(store, sid):
        scores, valid = _measurements(store, member)
        if not valid:
            return {}, False
        for key, score in scores.items():
            previous = combined.get(key)
            if previous is None or int(score["run_id"][4:]) > int(
                previous["run_id"][4:]
            ):
                combined[key] = score
    return combined, True


def compare_routes(actions, pid, baseline, candidate):
    routes = {r["id"]: r for r in project_routes(actions, pid)["routes"]}
    if baseline not in routes or candidate not in routes:
        raise KeyError("项目中没有指定的研究路线")
    if baseline == candidate:
        raise ValueError("请选两条不同的研究路线")
    store = actions.store
    a, b = _registered_files(store, baseline), _registered_files(store, candidate)
    shared = a.keys() & b.keys()
    files = {
        "added": sorted(b.keys() - a.keys()),
        "removed": sorted(a.keys() - b.keys()),
        "changed": sorted(p for p in shared if a[p] and b[p] and a[p] != b[p]),
        "unchanged": sum(bool(a[p]) and a[p] == b[p] for p in shared),
        "unknown": sorted(p for p in shared if not a[p] or not b[p]),
    }
    left, ok_left = route_measurements(store, baseline)
    right, ok_right = route_measurements(store, candidate)
    rows = compare_measurements(left, right, ok_left and ok_right)
    return {
        "baseline": routes[baseline],
        "candidate": routes[candidate],
        "files": files,
        **rows,
    }


def compare_measurements(left, right, integrity_valid=True):
    if not integrity_valid:
        return {
            "comparisons": [],
            "comparison_note": "基准回执完整性校验失败，无法计算差值。",
        }
    comparisons = []
    for key in sorted(left.keys() & right.keys()):
        lscore, rscore = left[key], right[key]
        if lscore["run_id"] == rscore["run_id"]:
            continue  # A forked receipt is one experiment.
        n = lscore["planned_rows"]
        if (
            n <= 0
            or rscore["planned_rows"] != n
            or any(s.get("scored_rows", n) != n for s in (lscore, rscore))
        ):
            continue
        bid, _, method, metric, _, _ = key
        comparisons.append(
            {
                "benchmark_id": bid,
                "method": method,
                "metric": metric,
                "baseline": lscore["value"],
                "candidate": rscore["value"],
                "delta": rscore["value"] - lscore["value"],
                "baseline_n": lscore["planned_rows"],
                "candidate_n": rscore["planned_rows"],
                "baseline_run_id": lscore["run_id"],
                "candidate_run_id": rscore["run_id"],
                "baseline_plan_id": lscore["plan_id"],
                "candidate_plan_id": rscore["plan_id"],
                "scope": rscore["scope"],
                "provenance": rscore["provenance"],
            }
        )
    note = "差值为候选减基线。仅比较相同方法标签、任务、案例、种子、预算和评分口径下的完整独立运行。预测类指标使用冻结目标重新计分，适配器给分的指标还需匹配评分代码和输入。"
    if not comparisons:
        note = "两条路线尚无可比的完整独立运行。继承同一份实验回执只计一次。"
    return {"comparisons": comparisons, "comparison_note": note}
