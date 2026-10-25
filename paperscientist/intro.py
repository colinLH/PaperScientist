"""Standalone cinematic entrance; the research UI keeps its existing URLs."""
import mimetypes
from pathlib import Path

from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles


def mount_intro(app):
    # Some Windows registries identify WebP as text/plain. Keep texture delivery
    # independent of the host's file associations.
    mimetypes.add_type('image/webp', '.webp')
    root = Path(__file__).parent / 'static' / 'intro'
    app.mount('/intro-assets', StaticFiles(directory=root), name='intro-assets')

    @app.get('/welcome', include_in_schema=False)
    async def welcome():
        return FileResponse(root / 'index.html', headers={'Cache-Control': 'no-cache'})

    @app.middleware('http')
    async def entrance(request, call_next):
        if request.method == 'GET' and request.url.path == '/' and not any(
            key in request.query_params for key in ('workspace', 'session', 'project')
        ):
            return RedirectResponse('/welcome', status_code=307)
        return await call_next(request)
