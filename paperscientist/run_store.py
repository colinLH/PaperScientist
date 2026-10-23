"""Durable jobs and idempotent node receipts alongside the append-only transcript."""
from __future__ import annotations

import json
import uuid
from langchain_core.messages import messages_to_dict
from .store import dumps, now, short_title


OPEN_STATUSES = {"queued", "running", "recovering", "waiting_input", "paused", "error"}


class RunStore:
    def __init__(self, store, on_update=None):
        self.store = store
        self.on_update = on_update
        with store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS research_runs(
                    id TEXT PRIMARY KEY, session_id TEXT, status TEXT, objective TEXT,
                    config TEXT, pending TEXT, resume TEXT, preview TEXT, outcome TEXT,
                    error TEXT, created_at TEXT, updated_at TEXT);
                CREATE INDEX IF NOT EXISTS run_session ON research_runs(session_id,created_at);
                CREATE TABLE IF NOT EXISTS run_receipts(
                    run_id TEXT, node_key TEXT, status TEXT, result TEXT,
                    PRIMARY KEY(run_id,node_key));
                CREATE TABLE IF NOT EXISTS workspace_preferences(user_id TEXT PRIMARY KEY, data TEXT);
                CREATE TABLE IF NOT EXISTS run_inbox(id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, content TEXT, delivered INTEGER DEFAULT 0);
            """)

    def decode(self, row):
        if not row:
            return None
        data = dict(row)
        for key in ("config", "pending", "resume", "outcome"):
            data[key] = json.loads(data[key]) if data[key] else None
        return data

    def get(self, rid):
        with self.store.connect() as db:
            return self.decode(db.execute("SELECT * FROM research_runs WHERE id=?", (rid,)).fetchone())

    def latest(self, sid):
        with self.store.connect() as db:
            return self.decode(db.execute("SELECT * FROM research_runs WHERE session_id=? ORDER BY created_at DESC LIMIT 1", (sid,)).fetchone())

    def update(self, rid, **values):
        allowed = {"status", "pending", "resume", "preview", "outcome", "error", "config"}
        if set(values) - allowed:
            raise ValueError("Invalid run update")
        values = {k: dumps(v) if k in {"config", "pending", "resume", "outcome"} and v is not None else v for k, v in values.items()}
        values["updated_at"] = now()
        with self.store.connect() as db:
            db.execute("UPDATE research_runs SET " + ",".join(k+"=?" for k in values) + " WHERE id=?", (*values.values(), rid))
        run = self.get(rid)
        if run and self.on_update:
            self.on_update(run)
        return run

    def create(self, sid, objective, config):
        rid, stamp = uuid.uuid4().hex, now()
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT status FROM research_runs WHERE session_id=? ORDER BY created_at DESC LIMIT 1", (sid,)).fetchone()
            if current and current[0] in OPEN_STATUSES:
                raise ValueError("当前会话已有任务，请回答问题、继续执行或先停止")
            db.execute("INSERT INTO research_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                       (rid, sid, "queued", objective, dumps(config), None, None, "", None, "", stamp, stamp))
        return self.get(rid)

    def receipt(self, rid, key):
        with self.store.connect() as db:
            r = db.execute("SELECT * FROM run_receipts WHERE run_id=? AND node_key=?", (rid, key)).fetchone()
        return {**dict(r), "result": json.loads(r["result"])} if r else None

    def begin_tool(self, rid, key):
        with self.store.connect() as db:
            db.execute("INSERT OR IGNORE INTO run_receipts VALUES(?,?,'running','{}')", (rid, key))

    def commit(self, rid, key, result, messages=(), presentation=()):
        """Commit a node result and its transcript effects in one SQLite transaction."""
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT result FROM run_receipts WHERE run_id=? AND node_key=? AND status='done'", (rid, key)).fetchone()
            if old:
                return json.loads(old[0])
            run = db.execute("SELECT session_id FROM research_runs WHERE id=?", (rid,)).fetchone()
            if not run or not db.execute("SELECT 1 FROM sessions WHERE id=?", (run[0],)).fetchone():
                raise ValueError("会话已删除")
            sid = run[0]
            for message in messages:
                db.execute("INSERT INTO messages(session_id,payload,created_at) VALUES(?,?,?)", (sid, dumps(messages_to_dict([message])[0]), now()))
                if message.type == "human":
                    db.execute("UPDATE sessions SET title=? WHERE id=? AND title='新研究对话'", (short_title(message.content), sid))
            db.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now(), sid))
            db.execute("INSERT OR REPLACE INTO run_receipts VALUES(?,?,'done',?)", (rid, key, dumps(result)))
            # The canonical transcript and its final UI events share a transaction.
            if presentation and db.execute('SELECT 1 FROM ui_turns WHERE id=?', (rid,)).fetchone():
                for kind, data in presentation:
                    db.execute('INSERT INTO ui_events(session_id,turn_id,kind,data,created_at) VALUES(?,?,?,?,?)', (sid, rid, kind, dumps(data), now()))
        return result

    def answer(self, rid, question_id, answer):
        if not answer.strip() or len(answer) > 20000:
            raise ValueError("回答需为 1–20000 个字符")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            run = self.decode(db.execute("SELECT * FROM research_runs WHERE id=?", (rid,)).fetchone())
            if not run or run["status"] != "waiting_input" or (run["pending"] or {}).get("question_id") != question_id:
                raise ValueError("问题已回答或已失效，请刷新后查看当前问题")
            payload = {"question_id": question_id, "answer": answer.strip()}
            db.execute("UPDATE research_runs SET status='queued',resume=?,updated_at=? WHERE id=?", (dumps(payload), now(), rid))

    def preference(self, **updates):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            r = db.execute("SELECT data FROM workspace_preferences WHERE user_id='local'").fetchone()
            data = json.loads(r[0]) if r else {}
            if updates:
                data.update(updates)
                db.execute("INSERT OR REPLACE INTO workspace_preferences VALUES('local',?)", (dumps(data),))
        return data

    def enqueue(self, rid, message):
        with self.store.connect() as db:
            db.execute("INSERT INTO run_inbox(run_id,content) VALUES(?,?)", (rid, message))

    def deliver(self, rid):
        from langchain_core.messages import HumanMessage
        with self.store.connect() as db:
            rows = db.execute("SELECT id,content FROM run_inbox WHERE run_id=? AND delivered=0 ORDER BY id", (rid,)).fetchall()
        for mid, content in rows:
            self.commit(rid, "inbox:"+str(mid), {}, [HumanMessage(content=content)])
            with self.store.connect() as db:
                db.execute("UPDATE run_inbox SET delivered=1 WHERE id=?", (mid,))
