"""A separate UI/API namespace for keyword paper reading."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .obsidian_vaults import discover_vaults


class ReadingRequest(BaseModel):
    keywords: str = Field(min_length=2, max_length=500)
    count: int = Field(default=2, ge=1, le=4)


class ReadingAnswer(BaseModel):
    question_id: str
    answer: str = Field(min_length=1, max_length=10000)


class ArchiveConfig(BaseModel):
    vault_root: str = Field(min_length=1, max_length=4096)
    prefix: str = Field(default='AI安全', min_length=1, max_length=500)
    include_existing_notes: bool = True


def mount_reading_api(app, service):
    assets = Path(__file__).parent / 'static' / 'reading'

    @app.get('/reading', include_in_schema=False)
    async def reading_page():
        return FileResponse(assets / 'index.html', headers={'Cache-Control': 'no-cache'})

    @app.get('/reading-assets/{name}', include_in_schema=False)
    async def reading_asset(name: str):
        if name not in {'reading.css', 'reading.js'}:
            raise HTTPException(404)
        return FileResponse(assets / name, headers={'Cache-Control': 'no-cache'})

    def same_origin(request: Request):
        if request.method == 'POST':
            origin = request.headers.get('origin')
            if ((origin and origin != str(request.base_url).rstrip('/'))
                    or request.headers.get('sec-fetch-site') == 'cross-site'
                    or request.headers.get('content-type', '').split(';')[0] != 'application/json'):
                raise HTTPException(403, '请从本站精读页面提交操作')

    router = APIRouter(prefix='/api/reading', dependencies=[Depends(same_origin)])

    def require(rid):
        try:
            run = service.runs.require(rid)
            service.job(run['session_id'])
            if not service.archive_for(run['session_id']).same_location(service.archive):
                raise ValueError('请先切回此任务原来的仓库')
            return run
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.get('/status')
    def status():
        warnings = [service.config_error] if service.config_error else []
        try:
            records = service.archive.index()['records']
            reports = service.archive.reports()
        except (ValueError, OSError) as exc:
            records = []
            reports = []
            warnings.append(str(exc))
        return {'ready': service.settings.model != 'demo' and not warnings,
                'model': service.settings.model, 'vault': str(service.archive.root), 'config': service.archive.config(),
                'obsidian_url': service.archive.uri(), 'paper_count': len(records),
                'reports': reports, 'jobs': service.jobs(), 'warnings': warnings}

    @router.get('/vaults')
    def vaults():
        return {'vaults': discover_vaults(), 'config': service.archive.config()}

    @router.post('/archive/preview')
    def preview_archive(body: ArchiveConfig):
        try:
            return service.preview_archive(body.model_dump())[1]
        except (ValueError, OSError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post('/archive')
    async def configure_archive(body: ArchiveConfig):
        try:
            return await service.configure_archive(body.model_dump())
        except (ValueError, OSError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post('/jobs')
    async def start(body: ReadingRequest):
        try:
            return await service.start_reading(body.keywords, body.count)
        except (ValueError, OSError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.get('/jobs/{rid}')
    def get_job(rid: str):
        run = require(rid)
        # Compact persisted progress; never send raw model/tool prompts or credentials.
        events = service.store.events(run['session_id'], 50)
        progress = []
        for event in events:
            if event['kind'] in {'tool_start', 'tool_result', 'run_progress'}:
                data = event['data']
                progress.append({'kind': event['kind'], 'tool': data.get('name', data.get('tool', '')),
                                 'status': data.get('status', ''), 'time': event['created_at']})
        return {k: run[k] for k in ('id', 'session_id', 'status', 'preview', 'outcome', 'error', 'pending', 'updated_at')} | {'progress': progress}

    @router.post('/jobs/{rid}/stop')
    async def stop(rid: str):
        run = require(rid)
        await service.runs.stop(run['session_id'], expected_run_id=rid)
        return {'status': service.runs.require(rid)['status']}

    @router.post('/jobs/{rid}/continue')
    async def resume(rid: str):
        require(rid)
        try:
            async with service.start_lock:
                require(rid)  # Recheck the destination after obtaining the switch/start lock.
                if service.has_active_job(except_run=rid):
                    raise ValueError('另一个精读任务正在执行')
                run = await service.runs.continue_run(rid)
                return {'status': run['status']}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post('/jobs/{rid}/answer')
    async def answer(rid: str, body: ReadingAnswer):
        require(rid)
        try:
            run = await service.runs.answer(rid, body.question_id, body.answer)
            return {'status': run['status']}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.get('/report')
    def report(path: str):
        try:
            return {'html': service.archive.preview(path), 'obsidian_url': service.archive.uri(service.archive.public_file(path))}
        except (ValueError, OSError) as exc:
            raise HTTPException(404, '报告不可用：' + str(exc)) from exc

    @router.get('/file')
    def file(path: str):
        try:
            target = service.archive.public_file(path)
            return FileResponse(target, headers={'X-Content-Type-Options': 'nosniff'})
        except (ValueError, OSError) as exc:
            raise HTTPException(404, '文件不可用') from exc

    app.include_router(router)
