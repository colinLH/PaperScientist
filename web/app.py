"""
启动服务器
python -m uvicorn app:app --host 0.0.0.0 --port 8888 --reload
停止服务器
Get-NetTCPConnection -LocalPort 8888 | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force }
"""
import sys
import os
import re
import json
import uuid
from pathlib import Path
from typing import Optional

# Ensure parent dir is on path so collector/memory/verify are importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from pydantic import BaseModel
from dotenv import dotenv_values

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles


from contextlib import asynccontextmanager
from langchain.messages import HumanMessage, AIMessage, AIMessageChunk
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # pip install aiosqlite

from collector import create_search_agent, AVAILABLE_MODELS, _apply_env_overrides, update_active_models
from memory import _MEM_SHORT_PAPER, _MEM_SHORT_STORE
from verify import _has_paper_content
from chat_store import save_turn, load_session, list_sessions, delete_session

_agent = None
_DB_PATH = str(Path(__file__).parent.parent / "checkpoints.db")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent
    print("[startup] Initializing agent with AsyncSqliteSaver...")
    async with AsyncSqliteSaver.from_conn_string(_DB_PATH) as checkpointer:
        _agent = create_search_agent(checkpointer=checkpointer)
        print("[startup] Agent ready.")
        yield
    print("[shutdown] Agent checkpointer closed.")

"""
用 FastAPI lifespan + async with AsyncSqliteSaver.from_conn_string(...) 创建异步 checkpointer，传入 agent
_agent 在 lifespan 内全程有效，关闭时自动释放连接
"""
app = FastAPI(title="All-in-One Literature Collection and Conversational Assistant", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ROOT = Path(__file__).parent.parent
ENV_FILE = ROOT / ".env"
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Static / UI
# ---------------------------------------------------------------------------

@app.get("/")
async def serve_ui():
    return FileResponse(str(STATIC_DIR / "index.html"))


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@app.get("/api/models")
async def get_models():
    return AVAILABLE_MODELS


# ---------------------------------------------------------------------------
# Env config
# ---------------------------------------------------------------------------

@app.get("/api/env")
async def get_env():
    env = dotenv_values(ENV_FILE)
    masked = {}
    for k, v in env.items():
        if any(s in k for s in ["KEY", "PASSWORD", "SECRET", "TOKEN"]):
            masked[k] = "***" if v else ""
        else:
            masked[k] = v
    return masked


class EnvApplyRequest(BaseModel):
    overrides: dict


@app.post("/api/env/apply")
async def apply_env(body: EnvApplyRequest):
    _apply_env_overrides(body.overrides)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Session history
# ---------------------------------------------------------------------------

@app.get("/api/sessions")
async def api_list_sessions():
    return list_sessions()


@app.get("/api/sessions/{thread_id}")
async def api_get_session(thread_id: str):
    return load_session(thread_id)


@app.delete("/api/sessions/{thread_id}")
async def api_delete_session(thread_id: str):
    if not delete_session(thread_id):
        raise HTTPException(404, "Session not found")
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Paper collection/ Paper store memory
# ---------------------------------------------------------------------------

def _read_paper_memory(session_id: str) -> list:
    """Read collected papers from short-term memory for a given agent session_id."""
    session_dir = Path(_MEM_SHORT_PAPER) / session_id
    if not session_dir.is_dir():
        return []

    turn_dirs = sorted(
        [d for d in session_dir.iterdir() if d.is_dir() and d.name.startswith("turn_")],
        key=lambda d: d.name,
        reverse=True,
    )

    for turn_dir in turn_dirs:
        rounds = sorted(
            [f for f in turn_dir.iterdir() if f.name.endswith(".json") and "_tools" not in f.name],
            key=lambda f: f.name,
            reverse=True,
        )
        for rfile in rounds:
            try:
                data = json.loads(rfile.read_text(encoding="utf-8"))
                content = data.get("content", "")
                if _has_paper_content(content):
                    raw = content.strip()
                    if raw.startswith("```"):
                        raw = raw.split("\n", 1)[-1]
                        raw = raw.rsplit("```", 1)[0].strip()

                    start, end = raw.find("["), raw.rfind("]")
                    if start != -1 and end > start:
                        raw = raw[start:end + 1]
                    papers = json.loads(raw)

                    if isinstance(papers, list):
                        return papers
            except Exception:
                pass
    return []


def _read_store_memory(session_id: str) -> dict:
    session_dir = Path(_MEM_SHORT_STORE) / session_id
    if not session_dir.is_dir():
        return {"status": "no_data"}

    turn_dirs = sorted(
        [d for d in session_dir.iterdir() if d.is_dir() and d.name.startswith("turn_")],
        key=lambda d: d.name,
        reverse=True,
    )

    for turn_dir in turn_dirs:
        rounds = sorted(
            [f for f in turn_dir.iterdir() if f.name.endswith(".json") and "_tools" not in f.name],
            key=lambda f: f.name,
        )
        if not rounds:
            continue

        try:
            data = json.loads(rounds[-1].read_text(encoding="utf-8"))
            content = data.get("content", "")
            raw = content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
                raw = raw.rsplit("```", 1)[0].strip()

            start, end = raw.find("{"), raw.rfind("}")
            if start != -1 and end > start:
                raw = raw[start:end + 1]
            return json.loads(raw)

        except Exception:
            return {"raw": content}

    return {"status": "no_data"}


@app.get("/api/memory/papers/{session_id}")
async def api_get_papers(session_id: str):
    return _read_paper_memory(session_id)


@app.get("/api/memory/store/{session_id}")
async def api_get_store(session_id: str):
    return _read_store_memory(session_id)


# ---------------------------------------------------------------------------
# Chat streaming
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = None
    env_overrides: Optional[dict] = None


def _extract_chat_answer(raw: str) -> str:
    """Extract 'answer' field from chat_llm JSON response."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(raw).get("answer", raw)
    except Exception:
        return raw


def _extract_paper_output(raw: str) -> str:
    """Strip the Paper List JSON code block from collect_paper output; keep taxonomy/summary."""
    """collect_paper 不输出 JSON 代码块，
    _extract_paper_output 在去除 Paper List heading 后，再补一步：strip 所有剩余的 ```json/python/text ``` fenced block。"""

    raw = raw.strip()
    # If the entire response is a pure JSON array (prompt intent), skip it — papers shown in table
    if raw.startswith("["):
        s, e = raw.find("["), raw.rfind("]")
        if s != -1 and e > s:
            try:
                json.loads(raw[s:e + 1])
                return ""
            except Exception:
                pass
    # Remove any '## ... Paper List ...' heading + fenced code block immediately after it
    cleaned = re.sub(
        r'##[^\n]*[Pp]aper\s*[Ll]ist[^\n]*\n+```(?:json)?\n.*?```\s*',
        '',
        raw,
        flags=re.DOTALL,
    )
    # Remove any remaining fenced JSON/code blocks (structured output we don't want to display)
    cleaned = re.sub(r'```(?:json|python|text)?\s*\n.*?```', '', cleaned, flags=re.DOTALL)
    return cleaned.strip()


def _extract_mysql_output(raw: str) -> str:
    """Extract paper_summary + insert_result from mysql_process JSON response."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    s, e = raw.find("{"), raw.rfind("}")
    if s != -1 and e > s:
        raw = raw[s:e + 1]
    try:
        data = json.loads(raw)
        parts = []
        if data.get("paper_summary"):
            parts.append(data["paper_summary"])
        if data.get("insert_result"):
            parts.append(
                "**Database insert result:**\n```json\n"
                + json.dumps(data["insert_result"], indent=2, ensure_ascii=False)
                + "\n```"
            )
        return "\n\n".join(parts) if parts else raw
    except Exception:
        return raw


NODE_LABELS = {
    "classify_intent": "🧭 Classifying intent...",
    "chat_llm":        "💬 LLM is thinking...",
    "collect_paper":   "📚 Collecting papers...",
    "mysql_process":   "🗄️ Processing database...",
    "tool_node":       "🔍 Calling tools...",
}

FINAL_NODES = {"chat_llm", "collect_paper", "mysql_process"}


@app.post("/api/chat/{thread_id}")
async def chat_stream(thread_id: str, body: ChatRequest):
    async def generate():
        # Step 1: Apply model / env overrides for this request
        if body.model or body.env_overrides:
            update_active_models(
                selected_model=body.model,
                env_overrides=body.env_overrides,
            )

        config = {"configurable": {"thread_id": thread_id}}
        input_state = {"messages": [HumanMessage(content=body.message)]}

        full_response = ""
        mem_session_id = ""
        thinking_sent: set = set()
        last_streaming_node: str | None = None

        """
            1. 每轮astream调用产生的事件流细节

            messages 流 (token 级)
            └─ FINAL_NODES 的每个 token → yield sse("token")
                → 前端 renderStreamContent() 逐字显示（含 reasoning 原始 JSON）

            updates 流 (节点完成)
            └─ chat_llm 完成      → full_response = _extract_chat_answer(...)  # 只提取 answer
            └─ collect_paper 完成  → full_response += _extract_paper_output(...)  # 剔除 Paper List JSON 块
            └─ mysql_process 完成  → full_response += _extract_mysql_output(...)  # 只提取 paper_summary + insert_result

            done 事件
            └─ content = full_response (干净内容)
                → 前端 renderFinalContent() 用 Markdown 渲染，覆盖之前的 raw JSON 流
                
            [节点开始] → messages 事件（逐 token） → [节点结束] → updates 事件（一次）

            ——————————————————————————————————————————————————————————————————————————————————————————————————————————————————————

            2. 同一个thread不同turn之间的state传递机制

            Turn 1：astream({"messages": [HM("Q1")]}, config={"thread_id": "t1"})
                    └─ 图运行完毕到 END
                    └─ SqliteSaver 将完整 state 写入 DB：
                        { messages: [HM("Q1"), AM(tool_call), TM(result), AM("A1")],
                        session_id: "sid1", turn_num: 1, intent: "general", ... }
 
            Turn 2：astream({"messages": [HM("Q2")]}, config={"thread_id": "t1"})
                    └─ SqliteSaver 加载上面保存的 state
                    └─ 将输入 [HM("Q2")] 通过 reducer 追加到已有 messages 上
                    └─ 实际运行时 state["messages"] = [HM("Q1"), AM("A1"), HM("Q2")]
                    └─ 图从 START 重新执行（不是续跑），但携带完整历史

            checkpointer (储存到sqlite向量库中，防止服务器重启丢失)，存的是"完整 state 快照"，不是 delta            
            checkpointer 本质保存的是：
            每一步的 State Snapshot
            
            LangGraph 的图每次 invoke/astream 调用都是从 START 跑到 END 的一次完整执行。到达 END 只是本次调用结束，不是"图实例被销毁"。

            下次调用时：

            Step 1: LangGraph 从 checkpointer 加载 thread_id 对应的 checkpoint（上次 END 时的完整 state）

            Step 2: 将新输入通过各字段的 reducer 合并进去：
                messages 字段用的是 Annotated[list, operator.add]，所以新消息追加到历史末尾
                session_id/turn_num 这类字段没有 reducer，新值覆盖旧值（由 classify_intent_node 更新）

            Step 3: 从 START 重新运行整张图，但此时 state["messages"] 已包含完整历史，LLM 自然就有了上下文
        """

        def sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        try:
            async for stream_event in _agent.astream(
                input_state, config, stream_mode=["updates", "messages"]
            ):
                stream_type, data = stream_event

                if stream_type == "updates":
                    # Node state updates — use for thinking indicators & session_id capture
                    for node_name, update in data.items():
                        if node_name not in thinking_sent and node_name != "__end__":
                            thinking_sent.add(node_name)
                            label = NODE_LABELS.get(node_name, f"⚙️ {node_name}...")
                            yield sse("thinking", {"node": node_name, "message": label})

                        if node_name == "classify_intent" and isinstance(update, dict):
                            sid = update.get("session_id", "")
                            if sid:
                                mem_session_id = sid
                                yield sse("session_id", {"session_id": sid})
                                
                        if node_name in FINAL_NODES and isinstance(update, dict):
                            msgs = update.get("messages", [])
                            last = msgs[-1] if msgs else None
                            if last:
                                # Intermediate: LLM decided to call tools → show badges
                                for tc in getattr(last, "tool_calls", []):
                                    yield sse("tool_call", {
                                        "name": tc.get("name", ""),
                                        "input": str(tc.get("args", {}))[:300],
                                    })
                                
                                # Final: LLM produced content (no tool_calls) → extract clean answer
                                if getattr(last, "content", "") and not getattr(last, "tool_calls", []):
                                    if node_name == "chat_llm":
                                        full_response = _extract_chat_answer(last.content)
                                    elif node_name == "collect_paper":
                                        extracted = _extract_paper_output(last.content)
                                        if extracted:
                                            full_response = (full_response + "\n\n---\n\n" + extracted).strip()
                                    elif node_name == "mysql_process":
                                        full_response = (full_response + "\n\n---\n\n" + _extract_mysql_output(last.content)).strip()

                elif stream_type == "messages":
                    # Stream tokens for all FINAL_NODES; inject separator on node switch
                    msg_chunk, meta = data
                    node_name = meta.get("langgraph_node", "")
                    if isinstance(msg_chunk, AIMessageChunk) and node_name in FINAL_NODES:
                        content = msg_chunk.content
                        if content:
                            if last_streaming_node is not None and last_streaming_node != node_name:
                                yield sse("token", {"content": "\n\n---\n\n"})
                            last_streaming_node = node_name
                            yield sse("token", {"content": content})

        except Exception as e:
            print(f"[stream error] {e}")
            import traceback; traceback.print_exc()
            yield sse("error", {"message": str(e)})
            return

        # Persist turn to chat history
        save_turn(thread_id, body.message, full_response, mem_session_id, body.model or "default")

        # Attach paper data if any
        papers = _read_paper_memory(mem_session_id) if mem_session_id else []
        store_result = _read_store_memory(mem_session_id) if mem_session_id else {}

        yield sse("done", {
            "content": full_response,
            "mem_session_id": mem_session_id,
            "papers": papers,
            "store_result": store_result,
        })

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=False)
