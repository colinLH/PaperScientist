"""Project route notes, lineage and comparisons in the local research workbench."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from . import baseline_refs
from .research_routes import (
    RevisionConflict,
    compare_routes,
    project_routes,
    update_route,
)


class RouteNote(BaseModel):
    revision: int = Field(ge=0)
    reason: str = Field(max_length=1000)
    status: Literal["exploring", "supported", "rejected", "stopped"]
    outcome: str = Field(max_length=1000)
    next_step: str = Field(max_length=1000)


class RouteFork(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class BaselineExport(BaseModel):
    plan_id: str = Field(min_length=1, max_length=100)
    run_id: str = Field(min_length=1, max_length=100)


class BaselineAttachment(BaseModel):
    source_session_id: str = Field(min_length=1, max_length=100)
    artifact_id: str = Field(min_length=1, max_length=100)


def mount_routes_api(app, actions):
    def same_origin(request):
        origin = request.headers.get("origin")
        if (
            origin and urlsplit(origin).netloc != request.url.netloc
        ) or request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "仅允许当前工作台修改研究路线")

    @app.get("/api/projects/{pid}/routes")
    def routes(pid: str):
        try:
            return project_routes(actions, pid)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/projects/{pid}/routes/compare")
    def compare(pid: str, baseline: str, candidate: str):
        try:
            return compare_routes(actions, pid, baseline, candidate)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.put("/api/projects/{pid}/routes/{sid}")
    def save(pid: str, sid: str, body: RouteNote, request: Request):
        same_origin(request)
        try:
            update_route(
                actions.store,
                pid,
                sid,
                body.revision,
                body.model_dump(exclude={"revision"}),
            )
            return next(
                r for r in project_routes(actions, pid)["routes"] if r["id"] == sid
            )
        except (KeyError, StopIteration) as exc:
            raise HTTPException(404, "项目中没有这条研究路线") from exc
        except RevisionConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/projects/{pid}/routes/{sid}/fork")
    async def fork(pid: str, sid: str, body: RouteFork, request: Request):
        same_origin(request)
        reason = body.reason.strip()
        if not reason:
            raise HTTPException(422, "请填写分支想验证的问题")
        try:
            source = actions.target("session", sid)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        if source["project_id"] != pid:
            raise HTTPException(404, "项目中没有这条研究路线")
        try:
            child = await actions.fork_idle(source, reason=reason)
            return {"session_id": child, "project_id": pid}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    def baseline_action(pid, sid, action, *args):
        try:
            session = actions.target("session", sid)
            if session["project_id"] != pid:
                raise KeyError(sid)
        except (ValueError, KeyError) as exc:
            raise HTTPException(404, "项目中没有这条研究路线") from exc
        try:
            return action(actions.store, session, *args)
        except KeyError as exc:
            raise HTTPException(404, "找不到指定的已登记基线或源会话") from exc
        except (ValueError, OSError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/projects/{pid}/routes/{sid}/baselines")
    def baselines(pid: str, sid: str):
        return baseline_action(pid, sid, baseline_refs.list_baselines)

    @app.post("/api/projects/{pid}/routes/{sid}/baselines/export")
    def export_baseline(pid: str, sid: str, body: BaselineExport, request: Request):
        same_origin(request)
        return baseline_action(
            pid, sid, baseline_refs.export_baseline, body.plan_id, body.run_id
        )

    @app.post("/api/projects/{pid}/routes/{sid}/baselines/attach")
    def attach_baseline(pid: str, sid: str, body: BaselineAttachment, request: Request):
        same_origin(request)
        return baseline_action(
            pid,
            sid,
            baseline_refs.attach_baseline,
            body.source_session_id,
            body.artifact_id,
        )

    @app.get("/api/projects/{pid}/routes/{sid}/baselines/{artifact_id}/compare")
    def compare_baseline(pid: str, sid: str, artifact_id: str):
        return baseline_action(pid, sid, baseline_refs.compare_reference, artifact_id)
