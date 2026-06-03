import json
from pathlib import Path
from datetime import datetime

SESSIONS_DIR = Path(__file__).parent / "chat_sessions"
SESSIONS_DIR.mkdir(exist_ok=True)


def _session_path(thread_id: str) -> Path:
    return SESSIONS_DIR / f"{thread_id}.json"


def load_session(thread_id: str) -> dict:
    p = _session_path(thread_id)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"thread_id": thread_id, "created_at": datetime.now().isoformat(), "turns": []}


def save_turn(thread_id: str, user_msg: str, ai_response: str, mem_session_id: str = "", model: str = "") -> None:
    session = load_session(thread_id)
    session.setdefault("turns", []).append({
        "timestamp": datetime.now().isoformat(),
        "user": user_msg,  # 该turn的用户查询
        "assistant": ai_response,  # 该turn的所有页面显示结果 (提取出的一些AI最终回复)
        "mem_session_id": mem_session_id,  # 该turn所属的session
        "model": model,  # 该
    })
    session["updated_at"] = datetime.now().isoformat()
    session["preview"] = user_msg[:80]
    with open(_session_path(thread_id), "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)


def list_sessions() -> list:
    result = []
    for p in sorted(SESSIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            result.append({
                "thread_id": data["thread_id"],
                "preview": data.get("preview", ""),
                "updated_at": data.get("updated_at", data.get("created_at", "")),
                "turn_count": len(data.get("turns", [])),
            })
        except Exception:
            pass
    return result


def delete_session(thread_id: str) -> bool:
    p = _session_path(thread_id)
    if p.exists():
        p.unlink()
        return True
    return False
