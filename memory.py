import os
import json
import shutil
from datetime import datetime
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage, AIMessage, ToolMessage

load_dotenv()

_MEM_SHORT_PAPER = os.path.join(os.path.dirname(__file__), "memory", "short", "paper_collect")
_MEM_SHORT_STORE = os.path.join(os.path.dirname(__file__), "memory", "short", "data_store")
_MEM_LONG        = os.path.join(os.path.dirname(__file__), "memory", "long")


def _get_turn_dir(mem_dir: str, session_id: str, turn_num: int) -> str:
    """返回当前对话turn的目录"""
    """Return the directory path for a specific session turn."""
    return os.path.join(mem_dir, session_id, f"turn_{turn_num:03d}")


def _get_round_num(mem_dir: str, session_id: str, turn_num: int) -> int:
    """返回当前对话turn下的节点轮数"""
    """Return the next round number for a session/turn directory."""
    turn_dir = _get_turn_dir(mem_dir, session_id, turn_num)
    if not os.path.isdir(turn_dir):
        return 1
    return len([f for f in os.listdir(turn_dir) if f.endswith(".json") and "_tools" not in f]) + 1


def _save_tool_results(state_messages: list, session_id: str, turn_num: int, mem_dir: str = _MEM_SHORT_PAPER) -> None:
    """记忆存储机制1：Save ToolMessages from the last tool_node run as round_{n}_tools.json."""
    tool_msgs = []
    calling_ai_msg = None
    for msg in reversed(state_messages):
        if isinstance(msg, ToolMessage):
            tool_msgs.insert(0, msg)
        elif isinstance(msg, AIMessage):
            calling_ai_msg = msg
            break

    if not tool_msgs:
        return

    name_lookup = {tc["id"]: tc["name"] for tc in (getattr(calling_ai_msg, "tool_calls", None) or [])}
    turn_dir = _get_turn_dir(mem_dir, session_id, turn_num)
    os.makedirs(turn_dir, exist_ok=True)
    prev_round = _get_round_num(mem_dir, session_id, turn_num) - 1
    if prev_round == 0:
        return

    records = [
        {
            "step": i + 1,
            "name": name_lookup.get(msg.tool_call_id, getattr(msg, "name", None)),
            "tool_call_id": msg.tool_call_id,
            "content": msg.content,
        }
        for i, msg in enumerate(tool_msgs)
    ]
    fpath = os.path.join(turn_dir, f"round_{prev_round:03d}_tools.json")
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def _save_short_memory(response, session_id: str, turn_num: int, mem_dir: str = _MEM_SHORT_PAPER) -> None:
    """记忆存储机制2：Save this round's response to short-term memory (session/turn/round)."""
    turn_dir = _get_turn_dir(mem_dir, session_id, turn_num)
    os.makedirs(turn_dir, exist_ok=True)
    round_num = _get_round_num(mem_dir, session_id, turn_num)
    tool_calls = getattr(response, "tool_calls", None) or []
    record = {
        "session_id": session_id,
        "turn": turn_num,
        "timestamp": datetime.now().isoformat(),
        "round": round_num,
        "has_tool_calls": bool(tool_calls),
        "content": response.content,
    }
    if tool_calls:
        record["tool_calls"] = [
            {"step": i + 1, "name": tc["name"], "args": tc["args"]}
            for i, tc in enumerate(tool_calls)
        ]
    fpath = os.path.join(turn_dir, f"round_{round_num:03d}.json")
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


def _save_long_memory(query: str, session_id: str, turn_num: int) -> None:
    """记忆存储机制3：Save query to per-session long-term memory dir and global index."""
    # Per-session directory under long memory
    session_long_dir = os.path.join(_MEM_LONG, session_id)
    os.makedirs(session_long_dir, exist_ok=True)

    record = {
        "session_id": session_id,
        "turn": turn_num,
        "timestamp": datetime.now().isoformat(),
        "query": query,
    }
    record_str = json.dumps(record, ensure_ascii=False)

    # Per-session queries log
    with open(os.path.join(session_long_dir, "queries.jsonl"), "a", encoding="utf-8") as f:
        f.write(record_str + "\n")

    # Global index (used by _cleanup_duplicate_sessions)
    with open(os.path.join(_MEM_LONG, "queries.jsonl"), "a", encoding="utf-8") as f:
        f.write(record_str + "\n")
    
    # 保存所有的历史查询记录
    archive_path = os.path.join(_MEM_LONG, "all_history_queries.json")
    history = []

    if os.path.isfile(archive_path):
        with open(archive_path, "r", encoding="utf-8") as f:
            history = json.load(f)
    history.append(record)

    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _cleanup_duplicate_sessions(llm=None) -> dict:
    """短期记忆更新机制：通过LLM分析长期记忆中的每个会话中存在的各个turn的相似查询，只保留最新turn的短期记忆结果，删除其余short memory。"""

    fpath = os.path.join(_MEM_LONG, "queries.jsonl")
    if not os.path.isfile(fpath):
        return {"groups_found": 0, "sessions_deleted": 0}

    records = []
    with open(fpath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if len(records) < 2:
        return {"groups_found": 0, "sessions_deleted": 0}

    if llm is None:
        llm = init_chat_model("deepseek:deepseek-v4-pro")

    indexed_queries = "\n".join(f"{i}: {r['query']}" for i, r in enumerate(records))

    prompt = (
        "Below is a list of user queries in the format \"index: query content\".\n"
        "Please group queries with the same or highly similar semantics together, and return a pure JSON array where each element is a list of indices for one group (single queries should also be listed).\n"
        "Output only JSON, without any explanatory text. Example format: [[0,1],[2],[3,4,5]]\n\n"
        f"Query list:\n{indexed_queries}"
    )

    response = llm.invoke([HumanMessage(content=prompt)])
    content = response.content.strip()
    if "```" in content:
        content = content.split("```")[1].lstrip("json").strip()
    groups = json.loads(content)

    surviving_indices = set()
    sessions_deleted = 0
    groups_with_duplicates = 0

    for group in groups:
        if len(group) <= 1:
            surviving_indices.update(group)
            continue
        groups_with_duplicates += 1
        group_records = sorted(
            ((i, records[i]) for i in group),
            key=lambda x: x[1]["timestamp"],
            reverse=True,
        )
        surviving_indices.add(group_records[0][0])
        for _, rec in group_records[1:]:
            sid = rec["session_id"]
            for mem_dir in [_MEM_SHORT_PAPER, _MEM_SHORT_STORE]:
                sdir = os.path.join(mem_dir, sid)
                if os.path.isdir(sdir):
                    shutil.rmtree(sdir)
            long_sdir = os.path.join(_MEM_LONG, sid)
            if os.path.isdir(long_sdir):
                shutil.rmtree(long_sdir)
            sessions_deleted += 1

    surviving_records = [records[i] for i in sorted(surviving_indices)]
    with open(fpath, "w", encoding="utf-8") as f:
        for rec in surviving_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    return {"groups_found": groups_with_duplicates, "sessions_deleted": sessions_deleted}
