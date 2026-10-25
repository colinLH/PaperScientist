from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from langchain_core.messages import messages_from_dict, messages_to_dict

MEMORY_TYPES = {"user_profile", "project_memory", "topics", "session_memory", "automation_memory", "experience"}


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
        raise ValueError("ID must contain 1–100 letters, numbers, underscores or hyphens")
    return value


def dumps(value):
    return json.dumps(value, ensure_ascii=False, default=str)


def short_title(text, limit=32):
    """A readable fallback while a first-question title is being generated."""
    text = str(text).split("\n\n[Attached files]")[0]
    text = re.sub(r"https?://\S+|sk-[A-Za-z0-9_-]+", "", text)
    text = re.sub(r"^[\s#>*\-]+", "", text)
    text = re.sub(r"^(?:请你|请|帮我|我想要|我想|能否|可以)(?:帮我)?[，,\s]*", "", text)
    text = re.sub(r"\s+", " ", text).strip(" \"'。！？.!?")
    return (text[:limit-1] + "…" if len(text) > limit else text) or "新研究对话"


class Store:
    """Append-only history and versioned memory in SQLite, with transactional updates."""

    def __init__(self, data_dir: Path):
        self.root = Path(data_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "research.db"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sessions(
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, project_id TEXT NOT NULL,
                    parent_id TEXT, title TEXT, created_at TEXT, updated_at TEXT);
                CREATE TABLE IF NOT EXISTS messages(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
                    payload TEXT NOT NULL, created_at TEXT);
                CREATE INDEX IF NOT EXISTS message_session ON messages(session_id,id);
                CREATE TABLE IF NOT EXISTS memories(
                    id TEXT NOT NULL, version INTEGER NOT NULL, kind TEXT NOT NULL,
                    owner TEXT NOT NULL, content TEXT NOT NULL, sources TEXT NOT NULL,
                    deleted INTEGER DEFAULT 0, updated_at TEXT, PRIMARY KEY(id,version));
                CREATE INDEX IF NOT EXISTS memory_owner ON memories(kind,owner);
                CREATE TABLE IF NOT EXISTS projects(
                    owner TEXT PRIMARY KEY, state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS checkpoints(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, through_id INTEGER,
                    summary TEXT, restore TEXT, created_at TEXT);
                CREATE TABLE IF NOT EXISTS events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, kind TEXT,
                    data TEXT, created_at TEXT);
                CREATE TABLE IF NOT EXISTS papers(
                    id TEXT, owner TEXT, data TEXT, PRIMARY KEY(id,owner));
                CREATE TABLE IF NOT EXISTS artifacts(
                    id TEXT PRIMARY KEY, session_id TEXT, path TEXT, kind TEXT,
                    metadata TEXT, created_at TEXT);
                CREATE TABLE IF NOT EXISTS agents(
                    id TEXT PRIMARY KEY, parent_id TEXT, data TEXT);
                CREATE TABLE IF NOT EXISTS navigation(
                    user_id TEXT, kind TEXT, target TEXT, state TEXT,
                    PRIMARY KEY(user_id,kind,target));
                CREATE TABLE IF NOT EXISTS shares(
                    token TEXT PRIMARY KEY, user_id TEXT, session_id TEXT,
                    content TEXT, created_at TEXT);
                CREATE TABLE IF NOT EXISTS removed_items(
                    user_id TEXT, kind TEXT, target TEXT, PRIMARY KEY(user_id,kind,target));
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def session(self, sid: str, user_id="local", project_id="default", parent_id=None):
        for value in (sid, user_id, project_id):
            identifier(value)
        with self.connect() as db:
            if db.execute("SELECT 1 FROM removed_items WHERE user_id=? AND ((kind='session' AND target=?) OR (kind='project' AND target=?))",
                          (user_id, sid, project_id)).fetchone():
                raise ValueError("该项目或对话已删除，请新建对话")
            states = db.execute("SELECT state FROM navigation WHERE user_id=? AND ((kind='session' AND target=?) OR (kind='project' AND target=?))",
                                (user_id, sid, project_id)).fetchall()
            if any(json.loads(r[0]).get("archived") for r in states):
                raise ValueError("请先恢复归档的项目或对话")
            row = db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
            if row:
                if (row["user_id"], row["project_id"]) != (user_id, project_id):
                    raise ValueError("Session belongs to another user/project")
                return dict(row)
            stamp = now()
            db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?)",
                       (sid, user_id, project_id, parent_id, "新研究对话", stamp, stamp))
        return self.session(sid, user_id, project_id)

    def get_session(self, sid):
        with self.connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (identifier(sid),)).fetchone()
        return dict(row) if row else None

    def new_chat(self, project_id="default", user_id="local"):
        """Atomically reuse a genuinely unused root chat, including across clients."""
        identifier(project_id)
        identifier(user_id)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM removed_items WHERE user_id=? AND kind='project' AND target=?",
                          (user_id, project_id)).fetchone():
                raise ValueError("项目已删除")
            nav = db.execute("SELECT state FROM navigation WHERE user_id=? AND kind='project' AND target=?",
                             (user_id, project_id)).fetchone()
            if nav and json.loads(nav[0]).get("archived"):
                raise ValueError("请先恢复归档的项目")
            if project_id != "default" and not db.execute(
                "SELECT 1 FROM projects WHERE owner=? UNION SELECT 1 FROM sessions WHERE user_id=? AND project_id=?",
                (f"{user_id}/{project_id}", user_id, project_id)).fetchone():
                raise ValueError("项目不存在")
            has_runs = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_runs'").fetchone()
            query = """SELECT s.* FROM sessions s WHERE user_id=? AND project_id=? AND parent_id IS NULL
                AND NOT EXISTS(SELECT 1 FROM messages m WHERE m.session_id=s.id)
                AND NOT EXISTS(SELECT 1 FROM artifacts a WHERE a.session_id=s.id)
                AND NOT EXISTS(SELECT 1 FROM sessions c WHERE c.parent_id=s.id)
                AND NOT EXISTS(SELECT 1 FROM agents a WHERE a.id=s.id OR a.parent_id=s.id)
                AND NOT EXISTS(SELECT 1 FROM removed_items r WHERE r.user_id=s.user_id AND r.kind='session' AND r.target=s.id)
                AND NOT EXISTS(SELECT 1 FROM navigation n WHERE n.user_id=s.user_id AND n.kind='session'
                    AND n.target=s.id AND json_extract(n.state,'$.archived')=1)
            """
            if has_runs:
                query += " AND NOT EXISTS(SELECT 1 FROM research_runs r WHERE r.session_id=s.id)"
            for row in db.execute(query + " ORDER BY updated_at DESC, id", (user_id, project_id)).fetchall():
                folder = self.root / "workspaces" / row["id"]
                # Uploaded or hand-written files are a draft too; never discard them.
                try:
                    if folder.exists() and any(p.is_file() for p in folder.rglob("*")):
                        continue
                except OSError:
                    continue
                return dict(row)
            sid, stamp = uuid.uuid4().hex, now()
            db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?)",
                       (sid, user_id, project_id, None, "新研究对话", stamp, stamp))
            return dict(db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone())

    def sessions(self, user_id="local"):
        with self.connect() as db:
            return [dict(r) for r in db.execute(
                "SELECT s.*, (SELECT COUNT(*) FROM messages m WHERE m.session_id=s.id) AS message_count "
                "FROM sessions s WHERE parent_id IS NULL AND user_id=? ORDER BY updated_at DESC", (user_id,))]

    def project_list(self, user_id="local"):
        """Include existing session projects and newly created empty projects."""
        identifier(user_id)
        groups = {}
        for session in self.sessions(user_id):
            pid = session["project_id"]
            if pid not in groups:
                state = self.project(session)
                groups[pid] = {"id": pid, "name": state.get("name") or ("我的研究" if pid == "default" else pid), "folder_path": state.get("folder_path"), "sessions": []}
            groups[pid]["sessions"].append(session)
        with self.connect() as db:
            rows = db.execute("SELECT owner,state FROM projects WHERE owner LIKE ?", (user_id+"/%",)).fetchall()
        for row in rows:
            owner_user, pid = row["owner"].split("/", 1)
            if owner_user == user_id and pid not in groups:
                state = json.loads(row["state"])
                groups[pid] = {"id": pid, "name": state.get("name") or pid, "folder_path": state.get("folder_path"), "sessions": []}
        if not groups:
            with self.connect() as db:
                removed = db.execute("SELECT 1 FROM removed_items WHERE user_id=? AND kind='project' AND target='default'", (user_id,)).fetchone()
            if not removed:
                groups["default"] = {"id": "default", "name": "我的研究", "sessions": []}
        return list(groups.values())

    def create_project(self, name, user_id="local", folder_path=None):
        identifier(user_id)
        name = name.strip()
        if not name or len(name) > 80:
            raise ValueError("项目名称需为 1–80 个字符")
        from .project_folders import validate_folder
        folder_path = validate_folder(folder_path) if folder_path and folder_path.strip() else None
        pid = uuid.uuid4().hex
        self.update_project({"user_id": user_id, "project_id": pid, "id": "unused"}, {"name": name, "folder_path": folder_path})
        return {"id": pid, "name": name, "folder_path": folder_path}

    def project_folder(self, sid):
        session = self.get_session(sid)
        if not session or self.get_agent(sid).get("isolated_review"):
            raise ValueError("此会话不可访问项目源文件夹")
        folder = self.project(session).get("folder_path")
        if not folder:
            raise ValueError("当前项目未绑定源文件夹")
        from .project_folders import validate_folder
        return Path(validate_folder(folder))

    def set_title(self, sid, title, source="model"):
        title = short_title(title, 40)
        with self.connect() as db:
            db.execute("UPDATE sessions SET title=? WHERE id=?", (title, identifier(sid)))
        self.event(sid, "session_title", {"source": source})

    def has_generated_title(self, sid):
        with self.connect() as db:
            return db.execute("SELECT 1 FROM events WHERE session_id=? AND kind='session_title' LIMIT 1", (sid,)).fetchone() is not None

    def append(self, sid, message):
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM sessions WHERE id=?", (sid,)).fetchone():
                raise ValueError("对话不存在或已删除")
            cur = db.execute("INSERT INTO messages(session_id,payload,created_at) VALUES(?,?,?)",
                             (sid, dumps(messages_to_dict([message])[0]), now()))
            db.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now(), sid))
            if message.type == "human":
                db.execute("UPDATE sessions SET title=? WHERE id=? AND title='新研究对话'",
                           (short_title(message.content), sid))
            return cur.lastrowid

    def history(self, sid, after=0):
        with self.connect() as db:
            rows = db.execute("SELECT id,payload FROM messages WHERE session_id=? AND id>? ORDER BY id", (sid, after)).fetchall()
        return [(r["id"], messages_from_dict([json.loads(r["payload"])])[0]) for r in rows]

    def event(self, sid, kind, data):
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM sessions WHERE id=?", (sid,)).fetchone():
                return None
            return db.execute("INSERT INTO events(session_id,kind,data,created_at) VALUES(?,?,?,?)",
                              (sid, kind, dumps(data), now())).lastrowid

    def events(self, sid, limit=100):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM events WHERE session_id=? ORDER BY id DESC LIMIT ?", (sid, limit)).fetchall()
        return [{**dict(r), "data": json.loads(r["data"])} for r in reversed(rows)]

    def memory_owner(self, kind, session, task_id=None):
        user, project, sid = session["user_id"], session["project_id"], session["id"]
        if kind == "user_profile":
            return user
        if kind == "automation_memory":
            if not task_id:
                raise ValueError("automation_memory requires an explicit scheduled task ID")
            return f"{user}/{identifier(task_id)}"
        if kind in {"session_memory", "topics"}:
            return f"{user}/{project}/{sid}"
        return f"{user}/{project}"

    def active_skills(self, sid):
        with self.connect() as db:
            rows = db.execute("SELECT data FROM events WHERE session_id=? AND kind='skill_loaded' ORDER BY id DESC LIMIT 32", (sid,)).fetchall()
        result, seen = [], set()
        for row in rows:
            item = json.loads(row["data"])
            key = (item["name"], item.get("resource", "SKILL.md"))
            if key not in seen:
                seen.add(key)
                result.append(item)
            if len(result) == 8:
                break
        return list(reversed(result))

    def put_memory(self, kind, owner, content, sources, memory_id=None, deleted=False):
        if kind not in MEMORY_TYPES:
            raise ValueError("Unknown memory type")
        mid = memory_id or uuid.uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM memories WHERE id=? ORDER BY version DESC LIMIT 1", (mid,)).fetchone()
            if row and (row["kind"], row["owner"]) != (kind, owner):
                raise ValueError("Memory scope mismatch")
            version = row["version"] + 1 if row else 1
            db.execute("INSERT INTO memories VALUES(?,?,?,?,?,?,?,?)",
                       (mid, version, kind, owner, dumps(content), dumps(sources), int(deleted), now()))
        return {"id": mid, "version": version, "kind": kind}

    def memories(self, kind=None, owner=None, versions=False):
        query = "SELECT * FROM memories m WHERE 1=1"
        args = []
        if not versions:
            query += " AND version=(SELECT MAX(version) FROM memories x WHERE x.id=m.id) AND deleted=0"
        if kind:
            query += " AND kind=?"
            args.append(kind)
        if owner:
            query += " AND owner=?"
            args.append(owner)
        with self.connect() as db:
            rows = db.execute(query + " ORDER BY updated_at DESC", args).fetchall()
        return [{**dict(r), "content": json.loads(r["content"]), "sources": json.loads(r["sources"])} for r in rows]

    def injected_memory(self, session, scheduled_task_id=None):
        result = self.memories("user_profile", self.memory_owner("user_profile", session))[:4]
        project_memory = self.memories("project_memory", self.memory_owner("project_memory", session))
        # Turn summaries must not crowd confirmed constraints out of the context.
        result.extend([m for m in project_memory if m["content"].get("origin") != "session_summary"][:6])
        result.extend([m for m in project_memory if m["content"].get("origin") == "session_summary"][:3])
        prefix = f"{session['user_id']}/{session['project_id']}/"
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        topics = [m for m in self.memories("topics") if m["owner"].startswith(prefix) and m["updated_at"] >= cutoff]
        result.extend(topics[:3])
        if scheduled_task_id:
            result.extend(self.memories("automation_memory", self.memory_owner("automation_memory", session, scheduled_task_id))[:1])
        return result

    def project(self, session):
        owner = self.memory_owner("project_memory", session)
        with self.connect() as db:
            row = db.execute("SELECT state FROM projects WHERE owner=?", (owner,)).fetchone()
        return json.loads(row[0]) if row else {"direction": "", "direction_confirmed": False, "stage": "exploration", "plan": [], "claims": []}

    def update_project(self, session, patch):
        owner = self.memory_owner("project_memory", session)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM projects WHERE owner=?", (owner,)).fetchone()
            state = json.loads(row[0]) if row else self.project(session)
            state.update(patch)
            db.execute("INSERT OR REPLACE INTO projects VALUES(?,?)", (owner, dumps(state)))
        return state

    def checkpoint(self, sid):
        with self.connect() as db:
            r = db.execute("SELECT * FROM checkpoints WHERE session_id=? ORDER BY id DESC LIMIT 1", (sid,)).fetchone()
        return {**dict(r), "restore": json.loads(r["restore"])} if r else None

    def save_checkpoint(self, sid, through_id, summary, restore):
        with self.connect() as db:
            db.execute("INSERT INTO checkpoints(session_id,through_id,summary,restore,created_at) VALUES(?,?,?,?,?)",
                       (sid, through_id, summary, dumps(restore), now()))

    def workspace(self, sid):
        path = self.root / "workspaces" / identifier(sid)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def file(self, sid, relative):
        root = self.workspace(sid)
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or path == root:
            raise ValueError("File must be inside the session workspace")
        return path

    def artifact(self, sid, path, kind, metadata=None):
        path = Path(path).resolve()
        if not path.is_relative_to(self.workspace(sid)) or not path.is_file():
            raise ValueError("Artifact must be an existing workspace file")
        aid = uuid.uuid4().hex
        meta = {**(metadata or {}), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        with self.connect() as db:
            db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?)", (aid, sid, str(path), kind, dumps(meta), now()))
        return {"id": aid, "path": str(path.relative_to(self.workspace(sid))), "kind": kind, "metadata": meta}

    def artifacts(self, sid):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM artifacts WHERE session_id=? ORDER BY created_at", (sid,)).fetchall()
        return [{**dict(r), "metadata": json.loads(r["metadata"])} for r in rows]

    def add_paper(self, session, paper):
        key = paper.get("doi") or paper.get("url") or paper["title"]
        pid = "p" + hashlib.sha256(key.lower().encode()).hexdigest()[:12]
        owner = self.memory_owner("project_memory", session)
        data = {**paper, "id": pid, "retrieved_at": now()}
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO papers VALUES(?,?,?)", (pid, owner, dumps(data)))
        return data

    def papers(self, session):
        with self.connect() as db:
            rows = db.execute("SELECT data FROM papers WHERE owner=?", (self.memory_owner("project_memory", session),)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def save_agent(self, agent):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO agents VALUES(?,?,?)", (agent["id"], agent["parent_id"], dumps(agent)))

    def agents(self, parent):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT data FROM agents WHERE parent_id=?", (parent,))]

    def get_agent(self, agent_id):
        with self.connect() as db:
            row = db.execute("SELECT data FROM agents WHERE id=?", (agent_id,)).fetchone()
        return json.loads(row[0]) if row else {}

    def recover_agents(self):
        with self.connect() as db:
            rows = db.execute("SELECT data FROM agents").fetchall()
        for row in rows:
            data = json.loads(row[0])
            if data["status"] in {"running", "queued"}:
                data.update(status="interrupted", error="Server restarted; follow up to resume persisted child history.")
                self.save_agent(data)
