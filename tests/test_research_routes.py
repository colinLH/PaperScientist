"""Project lineage and comparisons pass through the real HTTP, execution and storage paths."""

import asyncio
import json

from fastapi.testclient import TestClient

from paperscientist.api import create_app
from paperscientist.benchmarks import plan_benchmark, register_benchmark, run_benchmark
from paperscientist.config import Settings
from paperscientist.runtime import AgentService
from paperscientist.tools import ToolSet


def service_at(path):
    return AgentService(Settings(data_dir=path, model="demo", skill_roots=()))


def test_routes_lineage_revision_agent_context_and_access(tmp_path):
    service = service_at(tmp_path)
    store = service.store
    store.session("main", project_id="lab")
    store.session("other", project_id="another")
    store.session("private", user_id="another-user", project_id="lab")
    store.session("review", project_id="lab", parent_id="main")
    p = store.file("main", "method.txt")
    p.write_text("baseline")
    store.artifact("main", p, "note")
    base = "/api/projects/lab/routes"
    with TestClient(create_app(service=service, with_ui=False)) as http:
        assert [r["id"] for r in http.get(base).json()["routes"]] == ["main"]
        for sid in ["private", "review", "other"]:
            assert (
                http.post(
                    base + "/" + sid + "/fork", json={"reason": "guess"}
                ).status_code
                == 404
            )
        bad = http.post(
            base + "/main/fork",
            json={"reason": "injected"},
            headers={"Origin": "https://evil.example"},
        )
        assert bad.status_code == 403
        fork = http.post(
            base + "/main/fork", json={"reason": "Measure effect of grammar change"}
        ).json()
        sid = fork["session_id"]
        routes = {r["id"]: r for r in http.get(base).json()["routes"]}
        assert routes[sid]["parent_id"] == "main" and routes[sid]["revision"] == 1
        assert routes[sid]["reason"] == "Measure effect of grammar change"
        args = {
            "revision": 1,
            "reason": "grammar",
            "status": "rejected",
            "outcome": "Token boundary mismatch",
            "next_step": "Try a fixed parser",
        }
        tools = {
            t.name: t
            for t in ToolSet(
                service, store.get_session(sid), service.settings, service.scheduler
            ).tools
        }
        assert tools["record_route_decision"].invoke(args)["revision"] == 2
        assert "Token boundary mismatch" in service.system_prompt(
            store.get_session("main"), service.settings
        )
        assert "Token boundary mismatch" not in service.system_prompt(
            store.get_session("other"), service.settings
        )
        assert http.put(base + "/" + sid, json=args).status_code == 409
        assert http.put(base + "/private", json=args).status_code == 404
        for name, value in [("method.txt", "improved"), ("log.txt", "done")]:
            f = store.file(sid, name)
            f.write_text(value)
            store.artifact(sid, f, "note")
        diff = http.get(
            base + "/compare", params={"baseline": "main", "candidate": sid}
        ).json()
        assert diff["files"] == {
            "added": ["log.txt"],
            "removed": [],
            "changed": ["method.txt"],
            "unchanged": 0,
            "unknown": [],
        }
        assert diff["comparisons"] == []
        assert (
            http.get(
                base + "/compare", params={"baseline": "main", "candidate": "private"}
            ).status_code
            == 404
        )
        assert (
            http.post(
                "/api/workspace/action",
                json={"kind": "project", "target": "lab", "action": "archive"},
            ).status_code
            == 200
        )
        assert all(r["archived"] for r in http.get(base).json()["routes"])
        assert (
            http.put(base + "/" + sid, json={**args, "revision": 2}).status_code == 409
        )
        assert (
            http.post(base + "/" + sid + "/fork", json={"reason": "oops"}).status_code
            == 409
        )
    with TestClient(
        create_app(service=service_at(tmp_path), with_ui=False)
    ) as restarted:
        assert (
            next(r for r in restarted.get(base).json()["routes"] if r["id"] == sid)[
                "outcome"
            ]
            == "Token boundary mismatch"
        )


def run_smoke(store, sid):
    store.file(sid, "cases.json").write_text(
        json.dumps([{"case_id": "one", "split": "test", "target": 1}])
    )
    store.file(sid, "grade.py").write_text(
        'import json\nfrom pathlib import Path\nPath("scores.json").write_text(json.dumps('
        '[{"case_id":"one","seed":1,"method":"m","status":"ok","prediction":1}]))'
    )
    register_benchmark(
        store,
        sid,
        {
            "id": "route-smoke",
            "title": "Smoke",
            "version": "v1",
            "task": "Check route comparison wiring",
            "license": "local",
            "license_notes": "Synthetic local fixture",
            "source_url": "https://github.com/colinLH/PaperScientist",
            "license_url": "https://github.com/colinLH/PaperScientist",
            "provenance": "local_synthetic",
            "splits": ["test"],
            "metrics": {"accuracy": "Exact prediction with missing rows zero"},
        },
    )
    proto = {
        "decision": "selected",
        "rationale": "Verify actual adapter receipts",
        "claim": "Compute one correct label",
        "task_match": "Synthetic adapter",
        "scope": "smoke",
        "split": "test",
        "adapter": "local_python",
        "script_path": "grade.py",
        "dataset_path": "cases.json",
        "result_path": "scores.json",
        "case_ids": ["one"],
        "methods": ["m"],
        "seeds": [1],
        "metrics": ["accuracy"],
        "evaluator_description": "Frozen label evaluator",
        "limitations": "No claim about scientific research",
        "budget": {
            "timeout_seconds": 20,
            "max_evaluations": 1,
            "hardware": "local CPU",
        },
    }
    plan = plan_benchmark(store, sid, "route-smoke", proto)
    result = asyncio.run(run_benchmark(store, sid, plan["plan_id"], True))
    return plan, result, proto


def test_compare_rechecks_real_receipts_and_excludes_inherited_runs(tmp_path):
    service = service_at(tmp_path)
    store = service.store
    source = store.session("left")
    sid = source["id"]
    plan, result, proto = run_smoke(store, sid)
    base = "/api/projects/default/routes"
    with TestClient(create_app(service=service, with_ui=False)) as http:
        child = http.post(
            base + "/left/fork", json={"reason": "Validate an independent repetition"}
        ).json()["session_id"]

        def compare():
            return http.get(
                base + "/compare", params={"baseline": sid, "candidate": child}
            ).json()

        assert (
            compare()["comparisons"] == []
        )  # Both branches presently only have the inherited receipt.
        repeat = asyncio.run(run_benchmark(store, child, plan["plan_id"], True))
        values = compare()["comparisons"]
        assert len(values) == 1
        assert (values[0]["baseline"], values[0]["candidate"], values[0]["delta"]) == (
            1,
            1,
            0,
        )
        assert values[0]["baseline_n"] == values[0]["candidate_n"] == 1
        assert (
            values[0]["baseline_run_id"] == result["run_id"]
            and values[0]["candidate_run_id"] == repeat["run_id"]
        )
        assert values[0]["provenance"] == "local_synthetic"
        # A different predictor still gets a directly comparable score against the pinned labels.
        store.file(child, "candidate.py").write_text(
            store.file(child, "grade.py")
            .read_text()
            .replace('"prediction":1', '"prediction":0')
        )
        changed = plan_benchmark(
            store,
            child,
            "route-smoke",
            {**proto, "script_path": "candidate.py", "result_path": "scores.json"},
        )
        asyncio.run(run_benchmark(store, child, changed["plan_id"], True))
        difference = compare()["comparisons"]
        assert len(difference) == 1
        assert (
            difference[0]["baseline"],
            difference[0]["candidate"],
            difference[0]["delta"],
        ) == (1, 0, -1)
        store.file(child, repeat["result_snapshot_path"]).write_text("[]")
        data = compare()
        assert not data["comparisons"] and "完整性" in data["comparison_note"]


def test_explicit_local_baseline_export_attachment_and_independent_comparison(tmp_path):
    service = service_at(tmp_path)
    store = service.store
    store.session("origin", project_id="project_a")
    dest = store.session("replicate", project_id="project_b")
    store.session("unrelated", user_id="different", project_id="project_a")
    store.file("origin", "private-draft.txt").write_text(
        "unpublished manuscript and API details"
    )
    store.artifact("origin", store.file("origin", "private-draft.txt"), "note")
    plan, run, _ = run_smoke(store, "origin")
    with TestClient(create_app(service=service, with_ui=False)) as http:
        a = "/api/projects/project_a/routes/origin/baselines"
        b = "/api/projects/project_b/routes/replicate/baselines"
        assert http.get(a).json()["runs"][0]["run_id"] == run["run_id"]
        query = {"plan_id": plan["plan_id"], "run_id": run["run_id"]}
        doc = http.post(a + "/export", json=query).json()
        assert (
            http.post(a + "/export", json=query).json()["artifact_id"]
            == doc["artifact_id"]
        )
        assert doc["summary"]["case_count"] == doc["summary"]["seed_count"] == 1
        assert doc["summary"]["cells"][0]["metric"] == "accuracy"
        summary_text = json.dumps(doc["summary"])
        assert all(
            text not in summary_text
            for text in ["unpublished", "grade.py", '"one"', 'case_ids"', 'prediction"']
        )
        ticket = {"source_session_id": "origin", "artifact_id": doc["artifact_id"]}
        assert (
            http.post(
                b + "/attach", json={**ticket, "source_session_id": "unrelated"}
            ).status_code
            == 404
        )
        attach = http.post(b + "/attach", json=ticket).json()
        assert attach["summary"] == doc["summary"]
        assert (
            http.post(b + "/attach", json=ticket).json()["artifact_id"]
            == attach["artifact_id"]
        )
        assert (
            len([p for p in store.workspace("replicate").rglob("*") if p.is_file()])
            == 1
        )
        assert not any(
            a["kind"] in {"execution", "benchmark_result", "benchmark_protocol"}
            for a in store.artifacts("replicate")
        )
        tools = {
            x.name: x
            for x in ToolSet(service, dest, service.settings, service.scheduler).tools
        }
        tool = tools["research_baseline"]
        assert not tool.invoke({"action": "list"})["runs"]
        assert not tool.invoke(
            {"action": "compare", "artifact_id": attach["artifact_id"]}
        )["comparisons"]
        _, rerun, _ = run_smoke(store, "replicate")
        comparison = http.get(b + "/" + attach["artifact_id"] + "/compare").json()[
            "comparisons"
        ]
        assert len(comparison) == 1 and comparison[0]["delta"] == 0
        assert (
            comparison[0]["baseline_run_id"] == run["run_id"]
            and comparison[0]["candidate_run_id"] == rerun["run_id"]
        )
        assert http.post(b + "/export", json=query).status_code == 409
        store.file("origin", doc["path"]).write_text("{}")
        assert http.post(b + "/attach", json=ticket).status_code == 409
        assert (
            len(
                http.get(b + "/" + attach["artifact_id"] + "/compare").json()[
                    "comparisons"
                ]
            )
            == 1
        )
        store.file("replicate", attach["path"]).write_text("{}")
        assert http.get(b + "/" + attach["artifact_id"] + "/compare").status_code == 409
        assert http.get(b).json()["attached"][0]["valid"] is False


def test_detached_pre_registered_benchmark_flows_into_route_comparison(tmp_path):
    import time

    from paperscientist import benchmarks
    from paperscientist.experiment_jobs import inspect_job
    from paperscientist.baseline_refs import export_baseline

    service = service_at(tmp_path)
    store = service.store
    source = store.session("original")
    plan, _, proto = run_smoke(store, source["id"])
    with TestClient(create_app(service=service, with_ui=False)) as api:
        root = "/api/projects/default/routes"
        child = api.post(
            root + "/original/fork",
            json={"reason": "Independent background evaluation"},
        ).json()["session_id"]

        def wait_job(name):
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                state = inspect_job(store, child, name)
                if state["status"] not in {"queued", "running"}:
                    assert state["status"] == "completed", state
                    return state["run_id"]
                time.sleep(0.08)
            raise AssertionError("Timed out waiting for real benchmark supervisor")

        run = asyncio.run(
            run_benchmark(
                store, child, plan["plan_id"], True, background_name="replication"
            )
        )
        rid = wait_job("replication")
        assert run["job"]["run_id"] == rid
        assert (
            asyncio.run(
                run_benchmark(
                    store, child, plan["plan_id"], True, background_name="replication"
                )
            )["job"]["run_id"]
            == rid
        )
        diff = api.get(
            root + "/compare", params={"baseline": "original", "candidate": child}
        ).json()
        assert [(r["candidate_run_id"], r["delta"]) for r in diff["comparisons"]] == [
            (rid, 0)
        ]
        assert (
            export_baseline(store, store.get_session(child), plan["plan_id"], rid)[
                "summary"
            ]["cells"][0]["value"]
            == 1
        )

        long_protocol = {
            **proto,
            "budget": {**proto["budget"], "timeout_seconds": 1200},
        }
        second = plan_benchmark(store, child, "route-smoke", long_protocol)
        launch = asyncio.run(run_benchmark(store, child, second["plan_id"], True))
        assert wait_job(second["plan_id"]) == launch["job"]["run_id"]
        audit = benchmarks.audit_benchmarks(store, child)
        assert audit["integrity_valid"] and not audit["pending_plans"]
        assert any(
            a["run_id"] == rid and a["exit_code"] == 0 for a in audit["attempts"]
        )


def test_coordinator_routes_can_use_direct_evaluator_evidence_without_review_leakage(
    tmp_path,
):
    from paperscientist.baseline_refs import export_baseline, list_baselines
    from paperscientist.research_routes import route_measurements

    service = service_at(tmp_path)
    store = service.store
    root = store.session("coordinator")
    for sid, isolated in [("evaluation", False), ("blind", True)]:
        store.session(sid, parent_id=root["id"])
        store.save_agent(
            {"id": sid, "parent_id": root["id"], "isolated_review": isolated}
        )
    plan, result, _ = run_smoke(store, "evaluation")
    _, hidden, _ = run_smoke(store, "blind")
    scores, valid = route_measurements(store, root["id"])
    assert valid and {s["run_id"] for s in scores.values()} == {result["run_id"]}
    available = list_baselines(store, root)["runs"]
    assert [r["run_id"] for r in available] == [result["run_id"]]
    export = export_baseline(store, root, plan["plan_id"], result["run_id"])
    assert (
        export["source_session_id"] == root["id"]
        and export["summary"]["evaluator_session_id"] == "evaluation"
    )
    assert hidden["run_id"] not in json.dumps(export)
