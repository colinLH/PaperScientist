"""Persistent local workspace operations, shared by the web UI and HTTP API."""
from __future__ import annotations

import html
import json
import shutil
import uuid
from pathlib import Path

from .store import dumps, identifier, now
from .workspace import Workspace


class WorkspaceActions:
    def __init__(self, service):
        self.service, self.store = service, service.store

    def metadata(self, kind, target):
        with self.store.connect() as db:
            row = db.execute("SELECT state FROM navigation WHERE user_id='local' AND kind=? AND target=?", (kind, target)).fetchone()
        return json.loads(row[0]) if row else {}

    def target(self, kind, target):
        identifier(target)
        if kind == "session":
            item = self.store.get_session(target)
            if item and item["user_id"] == "local" and not item["parent_id"]:
                return {**item, "name": item["title"]}
        elif kind == "project":
            item = next((p for p in self.store.project_list() if p["id"] == target), None)
            if item:
                return item
        raise ValueError("未找到该项目或对话")

    def patch(self, kind, target, **values):
        self.target(kind, target)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM navigation WHERE user_id='local' AND kind=? AND target=?", (kind, target)).fetchone()
            state = json.loads(row[0]) if row else {}
            state.update(values)
            db.execute("INSERT OR REPLACE INTO navigation VALUES('local',?,?,?)", (kind, target, dumps(state)))
        return state

    def groups(self, archived=False, query=""):
        result = []
        query = query.strip().casefold()
        for project in self.store.project_list():
            p = {**project, **self.metadata("project", project["id"])}
            sessions = [{**s, **self.metadata("session", s["id"])} for s in p["sessions"]]
            sessions = [s for s in sessions if bool(p.get("archived") or s.get("archived")) == archived]
            if bool(p.get("archived")) != archived and not sessions:
                continue
            if query and query not in p["name"].casefold():
                sessions = [s for s in sessions if query in s["title"].casefold()]
                if not sessions:
                    continue
            p["sessions"] = sorted(sessions, key=lambda s: not s.get("pinned", False))
            result.append(p)
        return sorted(result, key=lambda p: not p.get("pinned", False))

    def affected(self, kind, target):
        self.target(kind, target)
        with self.store.connect() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM sessions WHERE user_id='local'")]
        ids = {s["id"] for s in rows if (s["project_id"] == target if kind == "project" else s["id"] == target)}
        while True:
            children = {s["id"] for s in rows if s["parent_id"] in ids}
            if children <= ids:
                return ids
            ids |= children

    async def quiesce(self, ids):
        for sid in ids:
            await self.service.runs.stop(sid)
            await self.service.cancel_turn(sid)
            await self.service.scheduler.cancel_parent(sid)
            lock = self.service.locks.get(sid)
            if lock and lock.locked():
                raise ValueError("对话正在运行，请停止后再操作")

    async def execute(self, kind, target, action, value="", confirmed=False):
        item = self.target(kind, target)
        state = self.metadata(kind, target)
        result = {"note": "已更新", "navigate": None}
        if action == "rename":
            name = value.strip()
            if not name or len(name) > 80:
                raise ValueError("名称需为 1–80 个字符")
            if kind == "session":
                # Preserve exact user names; the event also prevents automatic retitling.
                with self.store.connect() as db:
                    db.execute("UPDATE sessions SET title=? WHERE id=?", (name, target))
                self.store.event(target, "session_title", {"source": "user"})
            else:
                self.store.update_project({"id": "unused", "user_id": "local", "project_id": target}, {"name": name})
            result["note"] = "已重命名"
        elif action in {"pin", "unread"}:
            field = {"pin": "pinned", "unread": "unread"}[action]
            self.patch(kind, target, **{field: not state.get(field, False)})
            result["note"] = ("已取消置顶" if state.get(field) else "已置顶") if action == "pin" else ("已标记为已读" if state.get(field) else "已标记为未读")
        elif action == "section":
            if len(value.strip()) > 40:
                raise ValueError("分区名称最多 40 个字符")
            self.patch(kind, target, section=value.strip())
            result["note"] = "已更新分区"
        elif action == "archive":
            ids = self.affected(kind, target)
            if not state.get("archived"):
                await self.quiesce(ids)
            self.patch(kind, target, archived=not state.get("archived", False))
            result.update(note="已恢复" if state.get("archived") else "已归档 · 可在左侧归档列表恢复", affected=list(ids))
        elif action == "delete":
            if not confirmed:
                raise ValueError("永久删除需要明确确认")
            ids = self.affected(kind, target)
            await self.quiesce(ids)
            self.delete(kind, target, ids)
            await self.service.runs.purge(ids)
            result.update(note="已永久删除", affected=list(ids))
        elif action == "fork" and kind == "session":
            if state.get("archived") or self.metadata("project", item["project_id"]).get("archived"):
                raise ValueError("请先恢复归档，再创建分叉")
            if self.service.locks.get(target) and self.service.locks[target].locked():
                raise ValueError("请先停止当前回答，再分叉完整历史")
            sid = self.fork(item, empty=value == "empty")
            result.update(note="已创建独立分叉 · 共享原项目记忆", navigate=sid)
        elif action == "share" and kind == "session":
            content = self.transcript(target)
            token = uuid.uuid4().hex
            with self.store.connect() as db:
                db.execute("INSERT INTO shares VALUES(?,?,?,?,?)", (token, "local", target, dumps(content), now()))
            result.update(note="只读快照；链接仅在能访问此本机服务的环境中可用", url="/share/"+token)
        elif action == "unshare" and kind == "session":
            with self.store.connect() as db:
                db.execute("DELETE FROM shares WHERE user_id='local' AND session_id=?", (target,))
            result["note"] = "已撤销此对话的所有分享链接"
        else:
            raise ValueError("此操作不适用于当前项目或对话")
        return result

    def transcript(self, sid):
        item = self.target("session", sid)
        return {"title": item["title"], "messages": Workspace(self.store).history(sid)}

    def markdown(self, sid):
        data = self.transcript(sid)
        return "# " + data["title"] + "\n\n" + "\n\n".join(
            "## " + ("用户" if m["role"] == "user" else "PaperScientist") + "\n\n" + m["content"] for m in data["messages"])

    def checked_workspace(self, sid):
        base = (self.store.root / "workspaces").resolve()
        path = base / identifier(sid)
        if path.is_symlink() or path.is_junction() or path.resolve().parent != base:
            raise ValueError("工作区路径异常，已取消文件操作")
        if path.exists() and any(p.is_symlink() or p.is_junction() for p in path.rglob("*")):
            raise ValueError("工作区含链接目录或文件，请先移除链接再操作")
        return path

    def fork(self, source, empty=False):
        sid, old = uuid.uuid4().hex, source["id"]
        src, dest = self.checked_workspace(old), self.checked_workspace(sid)
        if not empty and src.exists():
            shutil.copytree(src, dest)
        try:
            self.store.session(sid, project_id=source["project_id"])
            with self.store.connect() as db:
                if not empty:
                    for r in db.execute("SELECT payload,created_at FROM messages WHERE session_id=? ORDER BY id", (old,)).fetchall():
                        # Replace absolute workspace references inside nested tool payloads too.
                        def rewrite(obj):
                            if isinstance(obj, str):
                                return obj.replace(str(src), str(dest)).replace(src.as_posix(), dest.as_posix())
                            if isinstance(obj, list):
                                return [rewrite(x) for x in obj]
                            if isinstance(obj, dict):
                                return {k: rewrite(v) for k, v in obj.items()}
                            return obj
                        db.execute("INSERT INTO messages(session_id,payload,created_at) VALUES(?,?,?)", (sid, dumps(rewrite(json.loads(r[0]))), r[1]))
                    for a in self.store.artifacts(old):
                        relative = Path(a["path"]).resolve().relative_to(src)
                        new_path = dest / relative
                        if new_path.is_file():
                            db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?)", (uuid.uuid4().hex, sid, str(new_path), a["kind"], dumps({**a["metadata"], "forked_from": a["id"]}), now()))
                db.execute("UPDATE sessions SET title=? WHERE id=?", (source["title"] + " · 分叉", sid))
                db.execute("INSERT INTO events(session_id,kind,data,created_at) VALUES(?,?,?,?)", (sid, "session_title", dumps({"source": "fork"}), now()))
                db.execute("INSERT INTO navigation VALUES('local','session',?,?)", (sid, dumps({"forked_from": old})))
        except Exception:
            with self.store.connect() as db:
                db.execute("DELETE FROM sessions WHERE id=?", (sid,))
            if dest.exists():
                shutil.rmtree(dest)
            raise
        return sid

    def delete(self, kind, target, ids):
        # Stage only checked session folders outside the public artifact directory.
        paths = [self.checked_workspace(sid) for sid in ids]
        staging = (self.store.root / ".deleting" / uuid.uuid4().hex).resolve()
        if not staging.is_relative_to(self.store.root):
            raise ValueError("删除暂存路径异常")
        moved = []
        try:
            for path in paths:
                if path.exists():
                    staging.mkdir(parents=True, exist_ok=True)
                    dest = staging / path.name
                    shutil.move(str(path), str(dest))
                    moved.append((path, dest))
            with self.store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                owners = {f"local/{self.store.get_session(sid)['project_id']}/{sid}" for sid in ids}
                # Remove every version derived from deleted conversations, avoiding resurrection.
                memory_ids = set()
                for row in db.execute("SELECT * FROM memories"):
                    content, sources = json.loads(row["content"]), json.loads(row["sources"])
                    scoped_project = kind == "project" and row["owner"] == "local/" + target and row["kind"] in {"project_memory", "experience"}
                    owned = row["owner"] in owners or scoped_project
                    derived = (row["owner"] == "local" or row["owner"].startswith("local/")) and (
                        content.get("session_id") in ids or any(s.get("session_id") in ids for s in sources))
                    if owned or derived:
                        memory_ids.add(row["id"])
                db.executemany("DELETE FROM memories WHERE id=?", [(mid,) for mid in memory_ids])
                for sid in ids:
                    for table in ("messages", "events", "checkpoints", "artifacts", "shares"):
                        db.execute(f"DELETE FROM {table} WHERE session_id=?", (sid,))
                    db.execute("DELETE FROM agents WHERE id=? OR parent_id=?", (sid, sid))
                    db.execute("DELETE FROM sessions WHERE id=?", (sid,))
                    db.execute("DELETE FROM navigation WHERE user_id='local' AND kind='session' AND target=?", (sid,))
                    db.execute("INSERT OR IGNORE INTO removed_items VALUES('local','session',?)", (sid,))
                if kind == "project":
                    for table in ("projects", "papers"):
                        db.execute(f"DELETE FROM {table} WHERE owner=?", ("local/"+target,))
                    db.execute("DELETE FROM navigation WHERE user_id='local' AND kind='project' AND target=?", (target,))
                    db.execute("INSERT OR IGNORE INTO removed_items VALUES('local','project',?)", (target,))
        except Exception:
            for path, dest in reversed(moved):
                shutil.move(str(dest), str(path))
            raise
        if staging.exists():
            shutil.rmtree(staging)


def share_html(data):
    escape = html.escape
    body = "".join(f'<article><small>{"用户" if m["role"] == "user" else "PaperScientist"}</small><pre>{escape(m["content"])}</pre></article>' for m in data["messages"])
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escape(data['title'])} · PaperScientist</title><style>body{{color:#e5e5e5;background:#212121;font:15px/1.8 system-ui;max-width:860px;margin:50px auto;padding:0 24px}}small,p{{color:#aaa}}h1{{font-size:24px}}article{{padding:20px;background:#292929;border-radius:12px;margin:18px 0}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}}</style>
    <p>◈ PaperScientist · 只读分享快照</p><h1>{escape(data['title'])}</h1>{body}</html>'''
