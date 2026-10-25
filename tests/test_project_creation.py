import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import gradio as gr
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage

from paperscientist.api import create_app
from paperscientist.config import Settings
from paperscientist.runtime import AgentService
from paperscientist.store import Store, dumps
from paperscientist.tools import ToolSet
from paperscientist.workspace_actions import WorkspaceActions


def test_reuse_is_atomic_scoped_and_survives_restart(tmp_path):
    store = Store(tmp_path)
    project = store.create_project('研究')['id']
    with ThreadPoolExecutor(max_workers=8) as pool:
        chats = list(pool.map(lambda _: Store(tmp_path).new_chat(project), range(16)))
    assert len({s['id'] for s in chats}) == 1
    first = chats[0]['id']
    assert Store(tmp_path).new_chat(project)['id'] == first
    store.append(first, HumanMessage(content='比较两种记忆方法'))
    second = store.new_chat(project)['id']
    assert second != first
    other = store.create_project('另一个研究')['id']
    assert store.new_chat(other)['id'] not in {first, second}
    store.session('foreign', user_id='other', project_id=project)
    assert store.new_chat(project)['id'] == second


def test_reuse_excludes_archives_children_and_file_drafts(tmp_path):
    store = Store(tmp_path)
    pid = store.create_project('研究')['id']
    store.session('parent', project_id=pid)
    store.session('child', project_id=pid, parent_id='parent')
    store.session('archived', project_id=pid)
    with store.connect() as db:
        db.execute("INSERT INTO navigation VALUES('local','session','archived',?)", (dumps({'archived': True}),))
    store.session('upload', project_id=pid)
    path = store.file('upload', 'draft.csv')
    path.write_text('data')
    store.artifact('upload', path, 'upload')
    store.session('manual', project_id=pid)
    store.file('manual', 'notes.txt').write_text('unsent draft')
    session = store.new_chat(pid)
    assert session['id'] not in {'parent', 'child', 'archived', 'upload', 'manual'}
    with store.connect() as db:
        db.execute("INSERT INTO navigation VALUES('local','project',?,?)", (pid, dumps({'archived': True})))
    with pytest.raises(ValueError, match='归档'):
        store.new_chat(pid)
    with pytest.raises(ValueError, match='不存在'):
        store.new_chat('missing')


def test_project_folder_validation_persistence_and_safe_deletion(tmp_path):
    source = tmp_path / '带空格的 source'
    source.mkdir()
    (source / 'notes.txt').write_text('keep source', encoding='utf-8')
    settings = Settings(data_dir=tmp_path / 'state', model='demo', skill_roots=())
    service = AgentService(settings)
    with TestClient(create_app(settings, service=service, with_ui=False)) as client:
        assert client.post('/api/projects', json={'name':'   '}).status_code == 400
        for invalid in ['relative/path', str(source/'missing'), str(source/'notes.txt')]:
            assert client.post('/api/projects', json={'name':'invalid', 'folder_path':invalid}).status_code == 400
        unbound = client.post('/api/projects', json={'name':'不绑定', 'folder_path':''}).json()
        assert unbound['folder_path'] is None
        bound = client.post('/api/projects', json={'name':'绑定', 'folder_path':str(source)}).json()
        sid = client.post('/api/sessions', params={'project_id':bound['id']}).json()['id']
        restarted = Store(settings.data_dir)
        group = next(p for p in restarted.project_list() if p['id']==bound['id'])
        assert group['folder_path'] == str(source.resolve())
        assert restarted.project_folder(sid) == source.resolve()
        assert client.post('/api/workspace/action', json={'kind':'project','target':bound['id'],'action':'delete','confirmed':True}).status_code == 200
        assert (source/'notes.txt').read_text() == 'keep source'


def test_folder_browser_and_same_site_guard(tmp_path):
    (tmp_path/'子目录').mkdir()
    (tmp_path/'file.txt').write_text('not a folder')
    settings = Settings(data_dir=tmp_path/'state', model='demo', skill_roots=())
    with TestClient(create_app(settings, with_ui=False)) as client:
        result = client.get('/api/local-folders', params={'path':str(tmp_path)})
        assert result.status_code == 200
        assert '子目录' in [p['name'] for p in result.json()['folders']]
        assert 'file.txt' not in str(result.json())
        assert client.get('/api/local-folders', params={'path':str(tmp_path)}, headers={'Origin':'https://foreign.example'}).status_code == 403
        assert client.post('/api/projects', json={'name':'bad','folder_path':str(tmp_path)}, headers={'Origin':'https://foreign.example'}).status_code == 403
        assert client.get('/api/local-folders', params={'path':str(tmp_path/'absent')}).status_code == 400
        assert client.get('/api/local-folders', params={'offset':-1}).status_code == 422


def test_project_file_tools_are_read_only_and_scoped(tmp_path):
    source = tmp_path/'source'
    source.mkdir()
    (source/'notes.txt').write_text('real notes', encoding='utf-8')
    settings = Settings(data_dir=tmp_path/'state', model='demo', skill_roots=())
    service = AgentService(settings)
    try:
        project = service.store.create_project('材料', folder_path=str(source))
        session = service.store.new_chat(project['id'])
        tools = {t.name:t for t in ToolSet(service, session, settings).tools}
        assert tools['list_files'].invoke({'scope':'project'}) == [{'path':'notes.txt','bytes':10}]
        assert tools['read_file'].invoke({'path':'notes.txt','scope':'project'})['content']=='real notes'
        for bad in ['../outside.txt',str(source/'notes.txt')]:
            with pytest.raises(ValueError):
                tools['read_file'].invoke({'path':bad,'scope':'project'})
        tools['write_file'].invoke({'path':'notes.txt','content':'output copy'})
        assert (source/'notes.txt').read_text() == 'real notes'
        service.store.save_agent({'id':session['id'], 'parent_id':'parent', 'isolated_review':True})
        with pytest.raises(ValueError):
            tools['read_file'].invoke({'path':'notes.txt','scope':'project'})
    finally:
        asyncio.run(service.close())


def test_ui_new_chat_and_created_project_callback(tmp_path):
    settings = Settings(data_dir=tmp_path, model='demo', skill_roots=())
    service = AgentService(settings)
    app = create_app(settings, service=service)
    blocks = next(r.app.get_blocks() for r in app.routes if hasattr(getattr(r,'app',None),'get_blocks'))
    callbacks = {f.fn.__name__:f.fn for f in blocks.fns.values() if f.fn}
    async def exercise():
        project = service.store.create_project('研究')
        view = {'generation':0}
        selected = await callbacks['open_created_project']('', view, gr.EventData(None, {'id':project['id']}))
        first = selected[0]
        again = await callbacks['start_chat'](project['id'], first, view)
        assert again[0] == first
        assert 'value' not in again[13]  # Clicking new chat must not erase unsent text.
        assert service.runs.db.preference()['session_id'] == first
        service.runs.db.create(first, 'queued but no message yet', {'settings':{'allow_execution':False}})
        next_chat = await callbacks['start_chat'](project['id'], first, view)
        assert next_chat[0] != first
        assert WorkspaceActions(service).fork(service.store.get_session(first), empty=True) == next_chat[0]
        await service.close()
    asyncio.run(exercise())
