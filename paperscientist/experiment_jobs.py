"""Session-scoped, detached Python experiments with fixed inputs and ordinary execution receipts."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from . import artifacts
from .store import Store, identifier, now


ACTIVE = ("queued", "running")


def _get(store, sid, name):
    with store.connect() as db:
        row = db.execute(
            "SELECT * FROM experiment_jobs WHERE session_id=? AND name=?", (sid, name)
        ).fetchone()
    if row is None:
        raise ValueError("Unknown experiment job in this session")
    return dict(row)


def _alive(pid):
    if not pid:
        return False
    if os.name == "nt":
        # os.kill(pid, 0) is not a liveness probe on Windows.
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return ctypes.get_last_error() == 5  # access denied
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258  # WAIT_TIMEOUT
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _finish(store, sid, name, status, error=""):
    with store.connect() as db:
        db.execute(
            "UPDATE experiment_jobs SET status=?,error=?,updated=? WHERE session_id=? AND name=? "
            "AND status IN ('queued','running')",
            (status, error, now(), sid, name),
        )


def _summary(store, row):
    sid, rid, name = row["session_id"], row["run_id"], row["name"]
    if row["status"] in ACTIVE and not _alive(row["supervisor_pid"]):
        _finish(
            store,
            sid,
            name,
            "interrupted",
            "Supervisor exited before recording a terminal status. Inspect retained logs.",
        )
        row = _get(store, sid, name)
    return {
        "name": name,
        "session_id": sid,
        "run_id": rid,
        "status": row["status"],
        "cancel_requested": bool(row["cancel_requested"]),
        "workspace": f"background-experiments/{rid}",
        "updated_at": row["updated"],
        "error": row["error"],
    }


def active_jobs(store, sid):
    with store.connect() as db:
        rows = db.execute(
            "SELECT * FROM experiment_jobs WHERE session_id=? AND status IN ('queued','running')",
            (sid,),
        ).fetchall()
    return [
        job for row in rows if (job := _summary(store, dict(row)))["status"] in ACTIVE
    ]


def inspect_job(store, sid, name="", tail=4000):
    if not name:
        with store.connect() as db:
            rows = db.execute(
                "SELECT * FROM experiment_jobs WHERE session_id=? ORDER BY updated DESC LIMIT 50",
                (sid,),
            ).fetchall()
        return {"jobs": [_summary(store, dict(r)) for r in rows]}
    result = _summary(store, _get(store, sid, identifier(name)))
    rid = result["run_id"]
    limit = min(16000, max(0, int(tail)))
    for stream in ("stdout", "stderr"):
        relative = f"runs/{rid}.{stream}.txt"
        path = store.file(sid, relative)
        result[stream] = artifacts.log_tail(path, limit) if limit else ""
        result[stream + "_path"] = relative
    attach_receipt(store, result)
    return result


def attach_receipt(store, job):
    """An interrupted or tampered receipt must not prevent access to the original logs."""
    from .benchmarks import execution_receipt

    rid, sid = job["run_id"], job["session_id"]
    if job["status"] in ACTIVE or not store.file(sid, f"runs/{rid}.json").is_file():
        return
    try:
        receipt = execution_receipt(store, sid, rid)
    except (ValueError, OSError):
        job["receipt_error"] = (
            "Execution receipt is incomplete or its registered hash has changed."
        )
        return
    job.update(
        receipt_path=f"runs/{rid}.json",
        exit_code=receipt["exit_code"],
        output_files=receipt["output_files"],
        timed_out=receipt["timed_out"],
    )


def stop_job(store, sid, name):
    _get(store, sid, identifier(name))
    with store.connect() as db:
        db.execute(
            "UPDATE experiment_jobs SET cancel_requested=1, updated=? WHERE session_id=? AND name=? "
            "AND status IN ('queued','running')",
            (now(), sid, name),
        )
    return inspect_job(store, sid, name)


def start_job(store, sid, name, path, inputs, timeout, enabled, *, benchmark_plan=None):
    if not enabled:
        raise PermissionError(
            "Python execution is disabled; enable it for this trusted local experiment"
        )
    identifier(name)
    if type(timeout) is not int or not 1 <= timeout <= 86400:
        raise ValueError("timeout must be 1–86400 seconds")
    # Selected benchmark protocols additionally copy their own manifest, plan, adapter and case index.
    max_inputs = 260 if benchmark_plan else 256
    if not isinstance(inputs, list) or len(inputs) > max_inputs:
        raise ValueError(f"Supply a list of at most {max_inputs} workspace input files")
    root = store.workspace(sid)

    # Normalize all names before trusting them as relative paths in the launch directory.
    def local(pathname):
        return store.file(sid, pathname).relative_to(root).as_posix()

    script = local(path)
    files = sorted({script, *(local(f) for f in inputs)})
    request = {"script": script, "files": files, "timeout": timeout}
    if benchmark_plan:
        request["benchmark_plan"] = benchmark_plan

    def matches(db):
        row = db.execute(
            "SELECT spec FROM experiment_jobs WHERE session_id=? AND name=?",
            (sid, name),
        ).fetchone()
        if row is not None and json.loads(row["spec"])["request"] != request:
            raise ValueError("Job name already used for different inputs or settings")
        return row is not None

    with store.connect() as db:
        if matches(db):
            return inspect_job(store, sid, name, tail=0)
    if not script.endswith(".py") or any(
        not store.file(sid, f).is_file() for f in files
    ):
        raise ValueError("Select an existing Python script and regular input files")
    rid = f"run_{time.time_ns()}"
    folder = store.file(sid, f"background-experiments/{rid}")
    folder.parent.mkdir(parents=True, exist_ok=True)
    # Copy potentially large datasets outside SQLite's write lock, then atomically claim the name.
    with tempfile.TemporaryDirectory(dir=folder.parent) as tmp:
        stage = Path(tmp) / "work"
        checksums = {}
        for f in files:
            dest = stage / f
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(store.file(sid, f), dest)
            with dest.open("rb") as stream:
                checksums[f] = hashlib.file_digest(stream, "sha256").hexdigest()
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not matches(db):
                stage.rename(folder)
                try:
                    spec = json.dumps({"request": request, "sha256": checksums})
                    # The supervisor can only claim a committed row addressed to its own PID.
                    db.execute(
                        "INSERT INTO experiment_jobs(session_id,name,run_id,spec,status,updated) VALUES(?,?,?,?,?,?)",
                        (sid, name, rid, spec, "queued", now()),
                    )
                    bootstrap = (
                        "import sys; sys.path.insert(0,sys.argv[1]);"
                        "from paperscientist.experiment_jobs import worker; worker(*sys.argv[2:])"
                    )
                    cmd = [
                        sys.executable,
                        "-I",
                        "-c",
                        bootstrap,
                        str(Path(__file__).resolve().parents[1]),
                        str(store.root),
                        sid,
                        name,
                        rid,
                    ]
                    kwargs = (
                        {
                            "creationflags": subprocess.DETACHED_PROCESS
                            | subprocess.CREATE_NEW_PROCESS_GROUP
                        }
                        if os.name == "nt"
                        else {"start_new_session": True}
                    )
                    proc = subprocess.Popen(
                        cmd,
                        env=artifacts.python_environment(),
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        **kwargs,
                    )
                    threading.Thread(target=proc.wait, daemon=True).start()
                    db.execute(
                        "UPDATE experiment_jobs SET supervisor_pid=? WHERE run_id=?",
                        (proc.pid, rid),
                    )
                except BaseException:
                    shutil.rmtree(folder, ignore_errors=True)
                    raise
    return inspect_job(store, sid, name, tail=0)


async def _execute(store, sid, name, row):
    rid = row["run_id"]
    spec = json.loads(row["spec"])
    request = spec["request"]
    work = f"background-experiments/{rid}"
    for f, digest in spec["sha256"].items():
        with store.file(sid, f"{work}/{f}").open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                raise ValueError("Frozen experiment input changed before launch")
    if _get(store, sid, name)["cancel_requested"]:
        return "cancelled"
    task = asyncio.create_task(
        artifacts.run_python(
            store,
            sid,
            f"{work}/{request['script']}",
            True,
            request["timeout"],
            job_run_id=rid,
            execution_dir=work,
            frozen_inputs=spec["sha256"],
        )
    )
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=0.35)
            if not task.done() and _get(store, sid, name)["cancel_requested"]:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                return "cancelled"
        result = task.result()
        if plan_id := request.get("benchmark_plan"):
            from . import benchmarks

            plan = benchmarks._plan(store, sid, plan_id)
            benchmarks.finish_benchmark(store, sid, plan, result)
        if result["timed_out"]:
            return "timed_out"
        return "completed" if result["exit_code"] == 0 else "failed"
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


def worker(data_dir, sid, name, rid):
    store = Store(Path(data_dir))
    with store.connect() as db:
        claimed = db.execute(
            "UPDATE experiment_jobs SET status='running',updated=? WHERE session_id=? AND name=? "
            "AND run_id=? AND status='queued' AND supervisor_pid=?",
            (now(), sid, name, rid, os.getpid()),
        ).rowcount
    if not claimed:
        return
    try:
        status = asyncio.run(_execute(store, sid, name, _get(store, sid, name)))
    except Exception as exc:
        _finish(store, sid, name, "failed", f"{type(exc).__name__}: {exc}"[:1000])
    else:
        _finish(store, sid, name, status)
