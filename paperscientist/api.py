from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse, Response
from pydantic import BaseModel, Field

from .config import Settings
from .memory import text_content
from .runtime import AgentService
from .store import dumps, identifier
from .workspace_actions import WorkspaceActions, share_html


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=100000)
    model: str | None = None
    user_id: str = "local"
    project_id: str = "default"
    allow_execution: bool | None = None


class ProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class RunRequest(ChatRequest):
    continuous: bool = True
    max_steps: int = Field(default=60, ge=1, le=100)


class AnswerRequest(BaseModel):
    question_id: str
    answer: str = Field(min_length=1, max_length=20000)


class ContinueRequest(BaseModel):
    message: str = Field(default="", max_length=20000)


class WorkspaceActionRequest(BaseModel):
    kind: str
    target: str
    action: str
    value: str = Field(default="", max_length=1000)
    confirmed: bool = False


def snapshot(service, sid):
    session = service.store.get_session(sid)
    if not session:
        raise ValueError("Session not found")
    return {"session":session,
            "messages":[{"id":mid,"role":m.type,"content":m.content,"tool_calls":getattr(m,"tool_calls",[])} for mid,m in service.store.history(sid)],
            "memory":service.store.injected_memory(session), "project":service.store.project(session),
            "papers":service.store.papers(session), "artifacts":service.store.artifacts(sid),
            "subagents":service.store.agents(sid), "events":service.store.events(sid),
            "checkpoint":service.store.checkpoint(sid), "run":service.runs.db.latest(sid)}


def create_app(settings=None, service=None, with_ui=True):
    settings = settings or Settings.load()
    service = service or AgentService(settings)

    @asynccontextmanager
    async def lifespan(app):
        await service.runs.recover()
        yield
        await service.close()

    app = FastAPI(title="PaperScientist", version="0.2.0", lifespan=lifespan)
    app.state.service = service
    from .timeline_api import mount_timeline_api
    mount_timeline_api(app, service)
    workspace_actions = WorkspaceActions(service)

    @app.post("/api/workspace/action")
    async def workspace_action(body: WorkspaceActionRequest):
        try:
            return await workspace_actions.execute(body.kind, body.target, body.action, body.value, body.confirmed)
        except (ValueError, OSError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/workspace/navigation")
    async def navigation(archived: bool = False, query: str = ""):
        return workspace_actions.groups(archived, query)

    @app.get("/api/sessions/{sid}/transcript")
    async def transcript(sid: str):
        try:
            return {**workspace_actions.transcript(sid), "markdown": workspace_actions.markdown(sid)}
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/sessions/{sid}/markdown")
    async def markdown_export(sid: str):
        try:
            return Response(workspace_actions.markdown(sid), media_type="text/markdown; charset=utf-8",
                            headers={"Content-Disposition": f'attachment; filename="{identifier(sid)}.md"'})
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/share/{token}")
    async def shared_session(token: str):
        with service.store.connect() as db:
            row = db.execute("SELECT content FROM shares WHERE token=?", (token,)).fetchone()
        if not row:
            raise HTTPException(404, "分享已撤销或对话已删除")
        return HTMLResponse(share_html(json.loads(row[0])), headers={"Cache-Control": "no-store", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'", "Referrer-Policy": "no-referrer"})

    @app.get("/api/health")
    async def health():
        return {"status":"ok","version":"0.2.0","model":settings.model,"skills":len(service.catalog.skills),
                "execution_enabled":settings.allow_execution,"mode":"local personal research assistant"}

    @app.get("/api/models")
    async def models():
        return {"deepseek":["deepseek-chat","deepseek-reasoner"],"google_genai":["gemini-2.5-flash"],
                "openai":["gpt-4.1"],"custom":"provider:model via PS_MODEL", "offline":["demo"]}

    @app.get("/api/sessions")
    async def sessions():
        return service.store.sessions()

    @app.get("/api/projects")
    async def projects():
        return service.store.project_list()

    @app.post("/api/projects")
    async def new_project(body: ProjectRequest):
        try:
            return service.store.create_project(body.name)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/sessions")
    async def new_session(project_id: str = "default"):
        try:
            return service.store.session(uuid.uuid4().hex,project_id=project_id)
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc

    @app.get("/api/sessions/{sid}")
    async def get_session(sid: str):
        try:
            return snapshot(service,sid)
        except ValueError as exc:
            raise HTTPException(404,str(exc)) from exc

    @app.post("/api/sessions/{sid}/runs")
    async def start_run(sid: str, body: RunRequest):
        try:
            if body.user_id != "local":
                raise ValueError("后台任务仅支持本地用户")
            cfg = settings.with_overrides(model=body.model, allow_execution=body.allow_execution, max_steps=body.max_steps)
            return await service.runs.start(sid, body.message, project_id=body.project_id, settings=cfg, continuous=body.continuous)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/runs/{rid}")
    async def get_run(rid: str):
        try:
            return service.runs.require(rid)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/api/runs/{rid}/answer")
    async def answer_run(rid: str, body: AnswerRequest):
        try:
            return await service.runs.answer(rid, body.question_id, body.answer)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/runs/{rid}/continue")
    async def continue_run(rid: str, body: ContinueRequest):
        try:
            return await service.runs.continue_run(rid, body.message)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/runs/{rid}/stop")
    async def stop_run(rid: str):
        try:
            run = service.runs.require(rid)
            await service.runs.stop(run["session_id"], expected_run_id=rid)
            return service.runs.require(rid)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/skills")
    async def skills(query: str = "", source: str = "", offset: int = 0, limit: int = 20):
        return {**service.catalog.search(query, limit, offset, source), "warnings":service.catalog.errors,
                "installed_total": len(service.catalog.skills)}

    @app.get("/api/skills/{name}")
    async def skill_detail(name: str, resource: str = "SKILL.md"):
        try:
            return {"name": name, "resource": resource, "content": service.catalog.load(name, resource)}
        except (ValueError, UnicodeError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/memory/papers/{sid}")
    async def papers(sid: str):
        session = service.store.get_session(sid)
        if not session:
            raise HTTPException(404,"Session not found")
        return service.store.papers(session)

    @app.get("/api/sessions/{sid}/export")
    async def export_session(sid: str):
        try:
            data = snapshot(service,sid)
        except ValueError as exc:
            raise HTTPException(404,str(exc)) from exc
        file = service.store.file(sid,"exports/session.json")
        file.parent.mkdir(exist_ok=True)
        file.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
        return FileResponse(file,filename=f"{sid}.json",media_type="application/json")

    @app.post("/api/chat/{sid}")
    async def chat(sid: str, body: ChatRequest):
        try:
            identifier(sid)
            service.store.session(sid,body.user_id,body.project_id)
            current = settings.with_overrides(model=body.model,allow_execution=body.allow_execution)
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc
        if service.locks.get(sid) and service.locks[sid].locked():
            raise HTTPException(409,"Session already running")
        async def events():
            async for event in service.stream(sid,body.message,settings=current,user_id=body.user_id,project_id=body.project_id):
                yield f"event: {event['type']}\ndata: {dumps(event['data'])}\n\n"
        return StreamingResponse(events(),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

    @app.post("/api/sessions/{sid}/upload")
    async def upload(sid: str, file: UploadFile = File(...)):
        if not service.store.get_session(sid):
            raise HTTPException(404,"Session not found")
        name = Path(file.filename or "upload.bin").name
        destination = service.store.file(sid,"uploads/"+uuid.uuid4().hex[:8]+"_"+name)
        destination.parent.mkdir(parents=True,exist_ok=True)
        content = await file.read(20_000_001)
        if len(content) > 20_000_000:
            raise HTTPException(413,"Upload limit is 20MB")
        destination.write_bytes(content)
        return service.store.artifact(sid,destination,"upload",{"origin":"user_upload"})

    @app.get("/api/artifacts/{aid}")
    async def download(aid: str):
        with service.store.connect() as db:
            row = db.execute("SELECT * FROM artifacts WHERE id=?",(aid,)).fetchone()
        if not row:
            raise HTTPException(404,"Artifact not found")
        path = Path(row["path"]).resolve()
        if not path.is_relative_to(service.store.workspace(row["session_id"])) or not path.is_file():
            raise HTTPException(404,"Artifact file unavailable")
        return FileResponse(path,filename=path.name)

    if with_ui:
        from .ui import mount_ui
        app = mount_ui(app,service)
    return app
