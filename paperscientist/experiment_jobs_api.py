"""Read experiment status and append-only log windows in the owning local workbench."""

import codecs
import os

from fastapi import HTTPException, Query

from .experiment_jobs import ACTIVE, _summary, attach_receipt
from .research_routes import route_members


def _log_window(path, offset, finished):
    if not path.exists():
        return "", 0
    with path.open("rb") as stream:
        size = stream.seek(0, os.SEEK_END)
        start = max(0, size - 8192) if offset is None else min(offset, size)
        stream.seek(start)
        raw = stream.read(16384)
        if offset is None and start:
            while raw and 128 <= raw[0] < 192:
                start += 1
                raw = raw[1:]
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        text = decoder.decode(raw, final=finished and start + len(raw) == size)
        remainder, _ = decoder.getstate()
        return text, start + len(raw) - len(remainder)


def mount_experiment_jobs_api(app, actions):
    store = actions.store

    def accessible(sid, run_id=None):
        try:
            root = actions.target("session", sid)
        except ValueError as exc:
            raise HTTPException(404, "对话不存在") from exc
        if store.get_agent(sid).get("isolated_review"):
            raise HTTPException(404, "对话不存在")
        params = route_members(store, root["id"])
        query = (
            "SELECT * FROM experiment_jobs j WHERE session_id IN ("
            + ",".join("?" for _ in params)
            + ")"
        )
        if run_id is not None:
            query += " AND j.run_id=?"
            params.append(run_id)
        with store.connect() as db:
            rows = db.execute(
                query + " ORDER BY j.updated DESC LIMIT 50", params
            ).fetchall()
        return [_summary(store, dict(row)) for row in rows]

    @app.get("/api/sessions/{sid}/experiments")
    def experiments(sid: str):
        return {"jobs": accessible(sid)}

    @app.get("/api/sessions/{sid}/experiments/{run_id}")
    def detail(
        sid: str,
        run_id: str,
        stdout_offset: int | None = Query(default=None, ge=0),
        stderr_offset: int | None = Query(default=None, ge=0),
    ):
        rows = accessible(sid, run_id)
        if not rows:
            raise HTTPException(404, "实验不存在")
        job = rows[0]
        owner = job["session_id"]
        for stream, offset in (("stdout", stdout_offset), ("stderr", stderr_offset)):
            path = store.file(owner, f"runs/{run_id}.{stream}.txt")
            job[stream], job[stream + "_offset"] = _log_window(
                path, offset, job["status"] not in ACTIVE
            )
        attach_receipt(store, job)
        return job
