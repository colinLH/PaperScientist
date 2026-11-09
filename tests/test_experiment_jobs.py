import asyncio
import concurrent.futures
import time

import pytest

from paperscientist.config import Settings
from paperscientist.experiment_jobs import inspect_job, start_job, stop_job
from paperscientist.runtime import AgentService
from paperscientist.store import Store
from paperscientist.tools import ToolSet


def wait_for(predicate, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.08)
    pytest.fail("experiment supervisor did not reach expected state")


def test_bound_tools_and_detached_receipt(tmp_path, monkeypatch):
    cfg = Settings.load(data_dir=tmp_path, allow_execution=True)
    service = AgentService(cfg)
    store = service.store
    session = store.session("job-test")
    sid = session["id"]
    tools = {t.name: t for t in ToolSet(service, session, cfg, service.scheduler).tools}
    monkeypatch.setenv("RESEARCH_API_KEY", "private-test-value")
    store.file(sid, "score.py").write_text(
        "from pathlib import Path\nimport os,time\n"
        "assert 'RESEARCH_API_KEY' not in os.environ\n"
        "print('warmup')\ntime.sleep(.9)\n"
        "Path('scores.csv').write_text('score\\n'+Path('input.txt').read_text()+'\\n')\n"
    )
    store.file(sid, "input.txt").write_text("3")
    params = {
        "name": "baseline",
        "path": "score.py",
        "inputs": ["input.txt"],
        "timeout": 3600,
    }

    def submit():
        return tools["start_experiment_job"].invoke(params)["run_id"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.map(lambda _: submit(), range(2))
    assert first == second
    store.file(sid, "input.txt").write_text("9")
    assert wait_for(lambda: "warmup" in inspect_job(store, sid, "baseline")["stdout"])
    # A fresh service can collect the detached worker's existing receipt.
    asyncio.run(service.close())
    service = AgentService(cfg)
    tools = {t.name: t for t in ToolSet(service, session, cfg, service.scheduler).tools}
    completed = wait_for(
        lambda: (
            r
            if (r := tools["inspect_experiment_job"].invoke({"name": "baseline"}))[
                "status"
            ]
            == "completed"
            else None
        )
    )
    assert completed["exit_code"] == 0
    path = completed["workspace"] + "/scores.csv"
    assert store.file(sid, path).read_text() == "score\n3\n"
    assert set(completed["output_files"]) == {path}
    evidence = tools["record_experiment"].invoke(
        dict(
            claim_id="claim",
            result_path=path,
            provenance="measured",
            evaluation_question="Recomputed score",
            run_id=first,
        )
    )
    assert evidence["metadata"]["run_id"] == first
    assert tools["inspect_experiment_job"].invoke({})["jobs"][0]["run_id"] == first
    with pytest.raises(ValueError, match="different"):
        tools["start_experiment_job"].invoke({**params, "timeout": 100})
    assert not inspect_job(store, "another")["jobs"]
    with pytest.raises(ValueError, match="Unknown"):
        stop_job(store, "another", "baseline")
    receipt_file = store.file(sid, completed["receipt_path"])
    receipt_file.write_text("{truncated", encoding="utf-8")
    assert "receipt_error" in inspect_job(store, sid, "baseline")
    with pytest.raises(ValueError, match="modified"):
        tools["record_experiment"].invoke(
            dict(
                claim_id="claim",
                result_path=path,
                provenance="measured",
                evaluation_question="Recomputed score",
                run_id=first,
            )
        )
    asyncio.run(service.close())


@pytest.mark.parametrize("stop,terminal", [(True, "cancelled"), (False, "timed_out")])
def test_stop_timeout_and_logs(tmp_path, stop, terminal):
    store = Store(tmp_path)
    path = store.file("s", "wait.py")
    path.write_text(
        "import subprocess,sys,time\n"
        "subprocess.Popen([sys.executable,'-c',\"import time,pathlib;time.sleep(2);pathlib.Path('orphan').touch()\"])\n"
        "print('child launched',flush=True)\ntime.sleep(20)"
    )
    name = "trial"
    with pytest.raises(PermissionError):
        start_job(store, "s", name, "wait.py", [], 5, False)
    with pytest.raises(ValueError, match="inside the session workspace"):
        start_job(store, "s", name, "wait.py", ["../private.txt"], 5, True)
    start_job(store, "s", name, "wait.py", [], 30 if stop else 1, True)
    wait_for(lambda: "child launched" in inspect_job(store, "s", name)["stdout"])
    if stop:
        stop_job(store, "s", name)
    result = wait_for(
        lambda: (
            r if (r := inspect_job(store, "s", name))["status"] == terminal else None
        )
    )
    assert "child launched" in result["stdout"]
    time.sleep(2.1)
    assert not (store.file("s", result["workspace"]) / "orphan").exists()


def test_workbench_job_visibility_and_utf8_cursors(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from paperscientist.experiment_jobs_api import mount_experiment_jobs_api
    from paperscientist.workspace_actions import WorkspaceActions

    cfg = Settings.load(data_dir=tmp_path)
    svc = AgentService(cfg)
    store = svc.store
    store.session("root")
    for sid, user, project, parent, isolated in (
        ("eva", "local", "default", "root", False),
        ("review", "local", "default", "root", True),
        ("foreign", "other", "default", None, False),
        ("another", "local", "default", None, False),
    ):
        store.session(sid, user, project, parent)
        if parent:
            store.save_agent(
                {"id": sid, "parent_id": parent, "isolated_review": isolated}
            )
        with store.connect() as db:
            db.execute(
                "INSERT INTO experiment_jobs(session_id,name,run_id,spec,status,updated) VALUES(?,?,?,?,?,?)",
                (sid, "score", "run_" + sid, "{}", "failed", "now"),
            )
    data = "x" * 16383 + "中" + "文"
    log = store.file("eva", "runs/run_eva.stdout.txt")
    log.parent.mkdir()
    log.write_text(data, encoding="utf-8")
    app = FastAPI()
    mount_experiment_jobs_api(app, WorkspaceActions(svc))
    client = TestClient(app)
    url = "/api/sessions/root/experiments"
    rows = client.get(url).json()["jobs"]
    assert [r["session_id"] for r in rows] == ["eva"]
    left = client.get(url + "/run_eva", params={"stdout_offset": 0}).json()
    right = client.get(
        url + "/run_eva", params={"stdout_offset": left["stdout_offset"]}
    ).json()
    assert left["stdout"] + right["stdout"] == data and right["stdout_offset"] == len(
        data.encode()
    )
    for sid in ("review", "another", "foreign"):
        assert client.get(url + "/run_" + sid).status_code == 404
    assert client.get("/api/sessions/eva/experiments").status_code == 404
    assert client.get("/api/sessions/foreign/experiments").status_code == 404
    asyncio.run(svc.close())
