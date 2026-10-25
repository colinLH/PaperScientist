"""Presentation helpers shared by the Python UI and workspace regression tests."""
from __future__ import annotations

import html
import hashlib
import os
import shutil
import uuid
from pathlib import Path

from .memory import text_content


class Workspace:
    def __init__(self, store):
        self.store = store

    def groups(self, query=""):
        query = query.strip().casefold()
        result = []
        for group in self.store.project_list():
            sessions = group["sessions"]
            if query and query not in group["name"].casefold():
                sessions = [s for s in sessions if query in s["title"].casefold()]
                if not sessions:
                    continue
            result.append({**group, "sessions": sessions})
        return result

    def name(self, pid):
        return next((p["name"] for p in self.store.project_list() if p["id"] == pid), pid)

    def history(self, sid):
        return [{"role": "user" if m.type == "human" else "assistant", "content": self.display_message(text_content(m)) if m.type == "human" else text_content(m)}
                for _, m in self.store.history(sid) if m.type == "human" or (m.type == "ai" and text_content(m).strip())]

    def downloads(self, sid, limit=80):
        """Serve bounded immutable snapshots, never files currently being overwritten."""
        root = self.store.workspace(sid)
        records = list(reversed(self.store.artifacts(sid)))
        records.sort(key=lambda a: a["kind"] not in {"manuscript_pdf", "bundle"})
        seen, paths = set(), []
        for item in records:
            source = Path(item["path"])
            if str(source) in seen:
                continue
            seen.add(str(source))
            expected = item["metadata"].get("sha256", "")
            if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
                continue
            dest = root / ".ui-cache" / expected / source.name
            try:
                if not source.resolve().is_relative_to(root) or not source.is_file():
                    continue
                if not dest.exists():
                    data = source.read_bytes()
                    if hashlib.sha256(data).hexdigest() != expected:
                        continue  # Wait for the next registered complete version.
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    temp = dest.with_name(uuid.uuid4().hex + ".tmp")
                    temp.write_bytes(data)
                    os.replace(temp, dest)
                paths.append(str(dest))
            except OSError:
                continue  # Windows may hold an exclusive writer lock for this version.
            if len(paths) >= limit:
                break
        return paths

    @staticmethod
    def display_message(text):
        message, marker, attachments = text.partition("\n\n[Attached files]\n")
        if not marker:
            return text
        return message + "\n\n" + " · ".join("📎 " + html.escape(Path(p).name[9:]) for p in attachments.splitlines() if p.strip())

    def attach(self, paths, sid, pid):
        sources = [Path(p) for p in paths or []]
        for source in sources:
            if not source.is_file() or source.stat().st_size > 20_000_000:
                raise ValueError("请选择有效文件；单个文件限 20MB")
        self.store.session(sid, project_id=pid)
        saved = []
        for source in sources:
            relative = "uploads/" + uuid.uuid4().hex[:8] + "_" + source.name
            dest = self.store.file(sid, relative)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            self.store.artifact(sid, dest, "upload", {"origin": "user_upload", "original_name": source.name})
            saved.append(relative)
        return saved

    def message(self, text, attachments, sid):
        text = text.strip() or ("请分析这些附件。" if attachments else "")
        if not text:
            raise ValueError("请输入研究需求或添加附件")
        if attachments:
            registered = {str(Path(a["path"]).relative_to(self.store.workspace(sid))).replace("\\", "/")
                          for a in self.store.artifacts(sid) if a["kind"] == "upload"}
            if any(p not in registered or not self.store.file(sid, p).is_file() for p in attachments):
                raise ValueError("附件不属于当前对话，请重新添加")
            text += "\n\n[Attached files]\n" + "\n".join(attachments)
        return text

    @staticmethod
    def chips(paths):
        return '<div class="attachment-chips">' + "".join(
            '<span>▤ ' + html.escape(Path(p).name[9:]) + '</span>' for p in paths) + '</div>'

    def heading(self, sid, pid):
        session = self.store.get_session(sid)
        title = session["title"] if session else "新对话"
        project = self.store.project(session or {"id": sid, "user_id": "local", "project_id": pid})
        folder = project.get("folder_path")
        hint = html.escape(folder or "未绑定源文件夹", quote=True)
        return '<div class="breadcrumb"><span title="' + hint + '">▱ ' + html.escape(self.name(pid)) + '</span><b>/</b><strong>' + html.escape(title) + '</strong></div>'

    def memory_cards(self, sid, pid):
        session = self.store.get_session(sid) or {"id": sid, "user_id": "local", "project_id": pid}
        entries = self.store.memories("project_memory", self.store.memory_owner("project_memory", session))
        name = html.escape(self.name(pid))
        result = f'<div class="memory-intro"><h2>{name} · 项目记忆</h2><p>同一项目的对话共享这些记录。每轮提炼重要内容，保留来源与版本。</p></div>'
        if not entries:
            return result + '<div class="memory-empty">项目记忆还是空的。开始研究后，这里会逐步积累决定、约束和会话摘要。</div>'
        for mem in entries[:40]:
            content = mem["content"]
            summary = content.get("origin") == "session_summary"
            label = "会话摘要 · 结论需核验" if summary else "用户确认的记忆"
            sources = []
            for ref in mem["sources"]:
                source = self.store.get_session(ref["session_id"]) if ref.get("session_id") else None
                if source:
                    sources.append(html.escape(source["title"]) + " · 消息 " + str(ref.get("message_id", "")))
            result += '<article class="memory-card"><small>' + label + ' · v' + str(mem["version"]) + '</small><p>' + html.escape(content.get("text", str(content))).replace('\n', '<br>') + '</p><footer>' + ' / '.join(dict.fromkeys(sources)) + '</footer></article>'
        return result
