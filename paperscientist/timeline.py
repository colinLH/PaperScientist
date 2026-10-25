"""Durable presentation events, independent of model context and graph checkpoints."""
from __future__ import annotations

import html
import json
from pathlib import Path
import re
import threading
from urllib.parse import unquote, urlparse

from langchain_core.messages import messages_from_dict
from markdown_it import MarkdownIt

from .memory import text_content
from .store import dumps, now, short_title


def category(name):
    if any(x in name for x in ('search', 'browse', 'fetch', 'read_paper', 'download_paper')):
        return 'search', '检索与阅读资料', 'globe'
    if name in {'write_file', 'edit_file', 'assemble_manuscript', 'stage_skill'}:
        return 'edit', '编辑文件', 'edit'
    if name in {'read_file', 'list_files', 'read_tool_result'}:
        return 'read', '查看文件', 'file'
    if name in {'run_python', 'compile_latex'}:
        return 'execute', '运行与验证', 'terminal'
    if name in {'figure_forge', 'review_manuscript', 'plot_results', 'draw_framework', 'validate_manuscript', 'export_bundle'}:
        return 'artifact', '生成与检查产物', 'chart'
    if any(x in name for x in ('subagent', 'agent_task', 'spawn', 'delegate')):
        return 'agent', '子代理协作', 'agents'
    if 'skill' in name:
        return 'skill', '使用技能', 'spark'
    if any(x in name for x in ('memory', 'remember', 'recall', 'research_plan', 'research_direction')):
        return 'memory', '记忆与研究计划', 'book'
    return 'other', '工具调用', 'tool'


def markdown(text, store, sid):
    """No raw HTML, remote images, or executable URLs from model/document content."""
    md = MarkdownIt('commonmark', {'html': False, 'breaks': True}).enable('table')
    tokens = md.parse(str(text))
    root = store.workspace(sid)
    for block in tokens:
        for token in block.children or []:
            if token.type == 'image':
                token.type, token.tag, token.content = 'text', '', '[图片：'+token.content+']'
            if token.type == 'link_open':
                href = unquote(token.attrGet('href') or '')
                if not urlparse(href).scheme or re.match(r'^[A-Za-z]:[/\\]', href):
                    try:
                        candidate = Path(href) if Path(href).is_absolute() else root / href
                        candidate = candidate.resolve()
                        if candidate.is_relative_to(root) and candidate.is_file():
                            token.attrSet('data-file', candidate.relative_to(root).as_posix())
                            token.attrSet('class', 'ps-inline-file')
                            token.attrSet('href', '#')
                    except (ValueError, OSError):
                        pass
                elif urlparse(href).scheme in {'https', 'http', 'mailto'}:
                    token.attrSet('target', '_blank')
                    token.attrSet('rel', 'noopener noreferrer')
                else:
                    token.attrSet('href', '#')
    return md.renderer.render(tokens, md.options, {})


class Timeline:
    def __init__(self, store, versions):
        self.store, self.versions = store, versions
        self._listeners = {}
        self._listeners_lock = threading.Lock()
        with store.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS ui_turns(
                    id TEXT PRIMARY KEY, session_id TEXT, start_message INTEGER,
                    end_message INTEGER, created_at TEXT);
                CREATE TABLE IF NOT EXISTS ui_events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, turn_id TEXT,
                    kind TEXT, data TEXT, created_at TEXT);
                CREATE INDEX IF NOT EXISTS ui_event_session ON ui_events(session_id,id);
            ''')

    def has(self, tid):
        with self.store.connect() as db:
            return db.execute('SELECT 1 FROM ui_turns WHERE id=?', (tid,)).fetchone() is not None

    def subscribe(self, sid, callback):
        """Process-local wakeups; SQLite remains the durable source of truth."""
        with self._listeners_lock:
            self._listeners.setdefault(sid, set()).add(callback)

        def unsubscribe():
            with self._listeners_lock:
                listeners = self._listeners.get(sid)
                if listeners is not None:
                    listeners.discard(callback)
                    if not listeners:
                        self._listeners.pop(sid, None)
        return unsubscribe

    def _notify(self, sid):
        with self._listeners_lock:
            listeners = tuple(self._listeners.get(sid, ()))
        for callback in listeners:
            try:
                callback()
            except RuntimeError:  # A disconnected client's event loop may have closed.
                pass

    def begin(self, sid, tid, objective):
        with self.store.connect() as db:
            start = (db.execute('SELECT MAX(id) FROM messages WHERE session_id=?', (sid,)).fetchone()[0] or 0) + 1
            cursor = db.execute('INSERT OR IGNORE INTO ui_turns VALUES(?,?,?,?,?)', (tid, sid, start, None, now()))
            if cursor.rowcount:
                data = {'id': tid, 'question': objective, 'title': short_title(objective, 60), 'status': 'queued', 'created_at': now()}
                db.execute('INSERT INTO ui_events(session_id,turn_id,kind,data,created_at) VALUES(?,?,?,?,?)', (sid, tid, 'turn', dumps(data), now()))
        if cursor.rowcount:
            self._notify(sid)

    def emit(self, sid, tid, kind, data):
        if not self.has(tid):
            return None
        with self.store.connect() as db:
            row = db.execute('INSERT INTO ui_events(session_id,turn_id,kind,data,created_at) VALUES(?,?,?,?,?)', (sid, tid, kind, dumps(data), now()))
        self._notify(sid)
        return row.lastrowid

    def status(self, run):
        if not self.has(run['id']):
            return
        self.emit(run['session_id'], run['id'], 'status', {k: run[k] for k in ('status', 'preview', 'error', 'pending')})

    def end(self, sid, tid):
        with self.store.connect() as db:
            end = db.execute('SELECT MAX(id) FROM messages WHERE session_id=?', (sid,)).fetchone()[0] or 0
            db.execute('UPDATE ui_turns SET end_message=? WHERE id=?', (end, tid))

    def after(self, sid, cursor, limit=300):
        with self.store.connect() as db:
            rows = db.execute('SELECT * FROM ui_events WHERE session_id=? AND id>? ORDER BY id LIMIT ?', (sid, cursor, limit)).fetchall()
        return [{**dict(r), 'data': json.loads(r['data'])} for r in rows]

    def files(self, sid, tid, declared=None, since=None, until=None):
        version = self.versions.get(sid, tid)
        if declared is None:
            with self.store.connect() as db:
                run = db.execute('SELECT outcome,created_at FROM research_runs WHERE id=? AND session_id=?', (tid, sid)).fetchone()
            if run:
                declared = (json.loads(run['outcome']) if run['outcome'] else {}).get('artifacts', [])
                since = since or run['created_at']
        refs, seen = [], set()
        root = self.store.workspace(sid)
        for rel in declared or []:
            try:
                p = self.store.file(sid, rel)
                if p.is_file():
                    refs.append({'path': p.relative_to(root).as_posix(), 'name': p.name})
                    seen.add(p.relative_to(root).as_posix())
            except (ValueError, OSError):
                continue
        changes = (version or {}).get('changes', [])
        for c in changes:
            if c['path'] not in seen and c['after'] and not c['undone']:
                refs.append({'path': c['path'], 'name': Path(c['path']).name})
                seen.add(c['path'])
        if not refs:
            for a in reversed(self.store.artifacts(sid)):
                if (since and a['created_at'] < since) or (until and a['created_at'] >= until):
                    continue
                try:
                    p = Path(a['path']).resolve()
                    rel = p.relative_to(root).as_posix()
                    if p.is_file() and rel not in seen:
                        refs.append({'path': rel, 'name': p.name})
                        seen.add(rel)
                except (ValueError, OSError):
                    pass
        def rank(ref):
            suffix = Path(ref['path']).suffix.lower()
            return ({'.pdf': 0, '.docx': 1, '.pptx': 2, '.xlsx': 3, '.html': 4, '.md': 5, '.csv': 6, '.zip': 7}.get(suffix, 8), 'figure' in ref['path'])
        refs.sort(key=rank)
        return {'files': refs[:12], 'primary': refs[0] if refs else None, 'changes': changes,
                'tracked': version is not None, 'skipped_files': (version or {}).get('skipped', 0)}

    def legacy(self, sid, owned):
        with self.store.connect() as db:
            # Tool bodies/artifacts can be megabytes. The timeline needs only their
            # status and call ID; full results remain available through tool-detail.
            rows = db.execute('''SELECT id,created_at,
                CASE WHEN json_extract(payload,'$.type')='tool'
                     THEN json_set(json_remove(payload,'$.data.artifact'),'$.data.content','')
                     ELSE payload END AS payload
                FROM messages WHERE session_id=? ORDER BY id''', (sid,)).fetchall()
            boundaries = [r[0] for r in db.execute('SELECT created_at FROM ui_turns WHERE session_id=?', (sid,))]
        turns, turn, calls = [], None, {}
        for row in rows:
            if any(start <= row['id'] <= (end or 10**18) for start, end in owned):
                continue
            message = messages_from_dict([json.loads(row['payload'])])[0]
            text = text_content(message)
            if message.type == 'human' and (turn is None or not text.startswith('关于“')):
                turn = {'id': 'history-'+str(row['id']), 'question': text, 'title': short_title(text, 60),
                        'created_at': row['created_at'], 'status': 'historical', 'items': [], 'legacy': True}
                turns.append(turn)
            if turn is None:
                continue
            if message.type == 'ai':
                if text:
                    turn['items'].append({'id': 'message-'+str(row['id']), 'type': 'assistant', 'text': text,
                                          'html': markdown(text, self.store, sid), 'state': 'complete'})
                for call in message.tool_calls:
                    cat, label, icon = category(call['name'])
                    item = {'id': call['id'], 'type': 'tool', 'name': call['name'], 'category': cat, 'label': label, 'icon': icon,
                            'args': self.argument_summary(call['args']), 'status': 'interrupted', 'message_id': row['id']}
                    calls[call['id']] = item
                    if call['name'] != 'finish_research':
                        turn['items'].append(item)
            elif message.type == 'tool' and message.tool_call_id in calls:
                item = calls[message.tool_call_id]
                item.update(status=getattr(message, 'status', 'success'), detail_message_id=row['id'])
            elif message.type == 'human' and text.startswith('关于“'):
                turn['items'].append({'id': 'answer-'+str(row['id']), 'type': 'note', 'text': text})
        # Associate output cards with their time window without inventing pre-edit versions.
        artifacts = self.store.artifacts(sid)
        for i, turn in enumerate(turns):
            future = [t['created_at'] for t in turns[i+1:i+2]] + [b for b in boundaries if b > turn['created_at']]
            until = min(future) if future else None
            candidates = [a for a in artifacts if a['created_at'] >= turn['created_at'] and (not until or a['created_at'] < until)]
            refs, seen = [], set()
            for a in reversed(candidates):
                try:
                    p = Path(a['path']).resolve(); rel = p.relative_to(self.store.workspace(sid)).as_posix()
                    if rel in seen or not p.is_file():
                        continue
                    seen.add(rel)
                    refs.append({'path': rel, 'name': p.name, 'kind': a['kind']})
                except (ValueError, OSError):
                    pass
            refs.sort(key=lambda r: (r['kind'] != 'manuscript_pdf', Path(r['path']).suffix.lower() not in {'.pdf', '.md', '.csv', '.zip'}))
            turn.update(files=refs[:8], primary=refs[0] if refs else None, changes=[], tracked=False)
        return turns

    @staticmethod
    def argument_summary(args):
        if not isinstance(args, dict):
            return str(args)[:350]
        priority = [args[k] for k in ('query', 'path', 'url', 'name', 'title', 'task', 'question', 'main_path') if args.get(k)]
        return ' · '.join(str(x)[:220] for x in priority) or ', '.join(args.keys())

    def snapshot(self, sid):
        with self.store.connect() as db:
            cursor = db.execute('SELECT COALESCE(MAX(id),0) FROM ui_events WHERE session_id=?', (sid,)).fetchone()[0]
            owners = db.execute('SELECT * FROM ui_turns WHERE session_id=? ORDER BY created_at', (sid,)).fetchall()
            rows = db.execute('SELECT * FROM ui_events WHERE session_id=? AND id<=? ORDER BY id', (sid, cursor)).fetchall()
        turns = self.legacy(sid, [(r['start_message'], r['end_message']) for r in owners])
        mapped, items = {}, {}
        for row in rows:
            d, tid, kind = json.loads(row['data']), row['turn_id'], row['kind']
            if kind == 'turn':
                mapped[tid] = {**d, 'items': [], 'files': [], 'changes': [], 'tracked': True}
            turn = mapped.get(tid)
            if not turn:
                continue
            key = (tid, d.get('id'))
            if kind == 'assistant_start':
                item = items.get(key)
                if item is None:
                    item = {'id': d['id'], 'type': 'assistant'}; items[key] = item; turn['items'].append(item)
                item.update(text='', html='', state='streaming')
            elif kind == 'assistant_delta' and key in items:
                items[key]['text'] += d['text']
            elif kind in {'assistant_commit', 'assistant_discard'}:
                if key not in items:
                    item = {'id': d['id'], 'type': 'assistant'}; items[key] = item; turn['items'].append(item)
                items[key].update(text=d.get('text', ''), state='complete' if kind.endswith('commit') else 'discarded')
                if kind == 'assistant_discard':
                    turn['items'].append({'id': 'retry-'+str(row['id']), 'type': 'note', 'text': d.get('reason', '')})
            elif kind == 'tool_start':
                if key not in items:
                    item = {**d, 'type': 'tool', 'status': 'running'}; items[key] = item; turn['items'].append(item)
            elif kind == 'tool_end' and key in items:
                items[key].update(d)
            elif kind == 'status':
                turn.update(d)
            elif kind == 'note':
                turn['items'].append({**d, 'type': 'note', 'id': 'event-'+str(row['id'])})
        for tid, turn in mapped.items():
            with self.store.connect() as db:
                run = db.execute('SELECT outcome,status FROM research_runs WHERE id=?', (tid,)).fetchone()
            outcome = json.loads(run['outcome']) if run and run['outcome'] else {}
            if run:
                turn['status'] = run['status']
            for item in turn['items']:
                if item['type'] == 'assistant':
                    item['html'] = markdown(item.get('text', ''), self.store, sid)
                    if item['state'] == 'streaming' and turn['status'] in {'error', 'stopped', 'recovering'}:
                        item['state'] = 'interrupted'
            until = min((t['created_at'] for t in mapped.values() if t['created_at'] > turn['created_at']), default=None)
            turn.update(self.files(sid, tid, outcome.get('artifacts'), since=turn['created_at'], until=until))
            turns.append(turn)
        turns.sort(key=lambda t: t['created_at'])
        return {'session_id': sid, 'cursor': cursor, 'turns': turns}


def mount(sid):
    return '<span class="ps-session-marker" data-session="'+html.escape(sid, quote=True)+'" hidden></span>'
