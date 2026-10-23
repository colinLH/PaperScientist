"""Per-turn workspace versions. Undo never overwrites an intervening edit."""
from __future__ import annotations

import difflib
import hashlib
import json
import os
from pathlib import Path
import uuid

from .store import dumps, identifier, now

MAX_BLOB = 20_000_000
EXCLUDED = {'.git', '.ui-cache', '__pycache__', '.pytest_cache', '.zig-cache', 'wheels', 'localappdata', '.venv', 'venv', 'node_modules', '.cache'}


class FileVersions:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS file_turns(
                id TEXT PRIMARY KEY, session_id TEXT, baseline TEXT, changes TEXT,
                skipped INTEGER, updated_at TEXT)''')
            db.execute('''CREATE TABLE IF NOT EXISTS file_undo_ops(
                id TEXT PRIMARY KEY, session_id TEXT, turn_id TEXT, paths TEXT, status TEXT)''')
        self.reconcile_undo()

    def reconcile_undo(self):
        """After a crash, recognize already restored files without overwriting anything."""
        with self.store.connect() as db:
            pending = db.execute("SELECT * FROM file_undo_ops WHERE status='pending'").fetchall()
        for op in pending:
            turn = self.get(op['session_id'], op['turn_id'])
            if turn:
                for change in turn['changes']:
                    if change['path'] not in json.loads(op['paths']):
                        continue
                    try:
                        p = self.store.file(op['session_id'], change['path'])
                        current = self.current_hash(p)
                        before = change['before']['sha'] if change['before'] else None
                        if current == before:
                            change['undone'] = True
                    except (ValueError, OSError):
                        continue
                with self.store.connect() as db:
                    db.execute('UPDATE file_turns SET changes=?,updated_at=? WHERE id=?', (dumps(turn['changes']), now(), turn['id']))
            with self.store.connect() as db:
                db.execute("UPDATE file_undo_ops SET status='reconciled' WHERE id=?", (op['id'],))

    def blob_path(self, sid, sha):
        if len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
            raise ValueError('无效的文件版本')
        return self.store.root / 'file-versions' / identifier(sid) / sha

    def save_blob(self, sid, data):
        sha = hashlib.sha256(data).hexdigest()
        target = self.blob_path(sid, sha)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(uuid.uuid4().hex + '.tmp')
            temp.write_bytes(data)
            os.replace(temp, target)
        return sha

    def scan(self, sid):
        root, result, skipped = self.store.workspace(sid), {}, 0
        def candidates():
            for directory, folders, files in os.walk(root, followlinks=False):
                folders[:] = [name for name in folders if name not in EXCLUDED and
                              not (Path(directory) == root and name == 'runs') and
                              (Path(directory) / name).resolve() == Path(directory) / name]
                yield from (Path(directory) / name for name in files)
        for p in candidates():
            rel = p.relative_to(root)
            if not p.is_file() or EXCLUDED.intersection(rel.parts) or rel.parts[0] == 'runs' or p.suffix in {'.db', '.pyc', '.log'} or p.name.endswith(('.db-wal', '.db-shm')):
                continue
            if not p.resolve().is_relative_to(root) or any(q.is_symlink() for q in (p, *p.parents) if q.is_relative_to(root)):
                skipped += 1
                continue
            try:
                if p.stat().st_size > MAX_BLOB:
                    skipped += 1
                    continue
                data = p.read_bytes()
                if len(data) > MAX_BLOB:
                    skipped += 1
                    continue
                result[rel.as_posix()] = {'sha': self.save_blob(sid, data), 'bytes': len(data)}
            except OSError:
                skipped += 1
        return result, skipped

    def begin(self, sid, tid):
        with self.store.connect() as db:
            if db.execute('SELECT 1 FROM file_turns WHERE id=?', (tid,)).fetchone():
                return
        baseline, skipped = self.scan(sid)
        with self.store.connect() as db:
            db.execute('INSERT OR IGNORE INTO file_turns VALUES(?,?,?,?,?,?)',
                       (tid, sid, dumps(baseline), '[]', skipped, now()))

    def get(self, sid, tid):
        with self.store.connect() as db:
            row = db.execute('SELECT * FROM file_turns WHERE id=? AND session_id=?', (tid, sid)).fetchone()
        return {**dict(row), 'baseline': json.loads(row['baseline']), 'changes': json.loads(row['changes'])} if row else None

    def finish(self, sid, tid):
        turn = self.get(sid, tid)
        if not turn:
            return []
        after, skipped = self.scan(sid)
        before, changes = turn['baseline'], []
        for path in sorted(before.keys() | after.keys()):
            old, new = before.get(path), after.get(path)
            if old == new:
                continue
            # A formerly tracked file exceeding the limit must not appear as deleted.
            actual = self.store.file(sid, path)
            if new is None and actual.exists():
                skipped += 1
                continue
            change = {'path': path, 'before': old, 'after': new, 'status': 'added' if old is None else 'deleted' if new is None else 'modified', 'undone': False}
            a, b = self.text(sid, old), self.text(sid, new)
            change.update(binary=a is None or b is None, added=0, removed=0)
            if a is not None and b is not None:
                for op, i, j, k, l in difflib.SequenceMatcher(a=a.splitlines(), b=b.splitlines()).get_opcodes():
                    if op in {'insert', 'replace'}:
                        change['added'] += l-k
                    if op in {'delete', 'replace'}:
                        change['removed'] += j-i
            changes.append(change)
        with self.store.connect() as db:
            db.execute('UPDATE file_turns SET changes=?,skipped=?,updated_at=? WHERE id=?', (dumps(changes), max(turn['skipped'], skipped), now(), tid))
        return changes

    def text(self, sid, version):
        if version is None:
            return ''
        if version['bytes'] > 500_000:
            return None
        try:
            text = self.blob_path(sid, version['sha']).read_bytes().decode('utf-8-sig')
            return None if '\0' in text else text
        except (OSError, UnicodeError):
            return None

    def diff(self, sid, tid, path):
        turn = self.get(sid, tid)
        change = next((c for c in (turn or {}).get('changes', []) if c['path'] == path), None)
        if not change:
            raise ValueError('这份历史文件没有可用的编辑前快照')
        a, b = self.text(sid, change['before']), self.text(sid, change['after'])
        lines = [] if a is None or b is None else list(difflib.unified_diff(a.splitlines(), b.splitlines(), fromfile='修改前/'+path, tofile='修改后/'+path, lineterm=''))
        return {**change, 'diff': '\n'.join(lines[:12000]), 'truncated': len(lines) > 12000}

    def version_data(self, sid, tid, path):
        turn = self.get(sid, tid) if tid else None
        change = next((c for c in (turn or {}).get('changes', []) if c['path'] == path), None)
        if change:
            version = change['before'] if change['undone'] else change['after']
            if version:
                return self.blob_path(sid, version['sha']).read_bytes(), '本轮文件快照'
            raise ValueError('此文件在选定版本中不存在')
        file = self.store.file(sid, path)
        if not file.is_file() or file.stat().st_size > 50_000_000:
            raise ValueError('文件不存在或超过 50 MB 预览限制')
        return file.read_bytes(), '当前文件（历史版本未保存）'

    def undo(self, sid, tid, paths=None):
        turn = self.get(sid, tid)
        if not turn:
            raise ValueError('历史对话没有编辑前快照，无法撤销')
        selected = [c for c in turn['changes'] if not c['undone'] and (paths is None or c['path'] in paths)]
        if not selected:
            raise ValueError('没有可撤销的更改')
        for change in selected:
            raw = self.store.workspace(sid) / change['path']
            if any(q.is_symlink() for q in (raw, *raw.parents) if q.is_relative_to(self.store.workspace(sid))):
                raise ValueError('路径已变为符号链接，无法撤销：'+change['path'])
            p = self.store.file(sid, change['path'])
            expected = change['after']['sha'] if change['after'] else None
            current = self.current_hash(p)
            if current != expected or p.is_symlink() or (p.exists() and not p.is_file()):
                raise ValueError('文件在本轮之后又被修改，已保留当前内容：'+change['path'])
            for version in (change['before'], change['after']):
                if version and hashlib.sha256(self.blob_path(sid, version['sha']).read_bytes()).hexdigest() != version['sha']:
                    raise ValueError('文件快照校验失败')
        operation = uuid.uuid4().hex
        with self.store.connect() as db:
            db.execute('INSERT INTO file_undo_ops VALUES(?,?,?,?,?)', (operation, sid, tid, dumps([c['path'] for c in selected]), 'pending'))
        applied = []
        try:
            for change in selected:
                self.restore(sid, change['path'], change['before'])
                applied.append(change)
        except OSError:
            for change in reversed(applied):
                self.restore(sid, change['path'], change['after'])
            with self.store.connect() as db:
                db.execute("UPDATE file_undo_ops SET status='rolled_back' WHERE id=?", (operation,))
            raise
        for change in selected:
            change['undone'] = True
        with self.store.connect() as db:
            db.execute('UPDATE file_turns SET changes=?,updated_at=? WHERE id=?', (dumps(turn['changes']), now(), tid))
            db.execute("UPDATE file_undo_ops SET status='done' WHERE id=?", (operation,))
        return {'restored': [c['path'] for c in selected], 'changes': turn['changes']}

    @staticmethod
    def current_hash(path):
        if not path.is_file():
            return None
        if path.stat().st_size > MAX_BLOB:
            return 'untracked-large-file'
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def restore(self, sid, path, version):
        target = self.store.file(sid, path)
        if version is None:
            # The after-image remains in the private version store; no original bytes are lost.
            target.unlink(missing_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name('.'+uuid.uuid4().hex+'.restore')
            temp.write_bytes(self.blob_path(sid, version['sha']).read_bytes())
            os.replace(temp, target)
