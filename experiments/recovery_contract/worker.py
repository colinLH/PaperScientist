"""One process lifetime. Crash via os._exit; never catches the injected exit."""
import asyncio
import json
import os
from pathlib import Path
import sys
import time
from typing import TypedDict

from common import audit, canonical, durable_json, observe, plan, record

ROOT = Path(sys.argv[1]).resolve()
CFG = json.loads((ROOT / "config.json").read_text())
sys.path.insert(0, CFG["snapshot"])
from paperscientist.store import Store
from paperscientist.run_store import RunStore
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

POLICY = CFG["policy"]
ITEMS = plan(CFG["n"], CFG["seed"])
EFFECT = ROOT / "effects.jsonl"
TRACE = ROOT / "trace.jsonl"
store = Store(ROOT / "metadata")
db = RunStore(store)
rid = json.loads((ROOT / "identity.json").read_text())["run_id"]


def trace(event, **fields):
    with TRACE.open("a", encoding="utf-8") as f:
        f.write(canonical({"event": event, "pid": os.getpid(), **fields}) + "\n")
        f.flush()
        os.fsync(f.fileno())


def crash(point, i):
    marker = ROOT / "crash.json"
    if CFG["point"] == point and CFG["target"] == i and not marker.exists():
        durable_json(marker, {"point": point, "i": i, "pid": os.getpid()})
        trace("hard_exit", point=point, i=i)
        os._exit(73)


class State(TypedDict, total=False):
    i: int
    blocked: bool
    reason: str
    reported_complete: bool


async def execute(state):
    i = state["i"]
    item, key = ITEMS[i], f"tool:{i}"
    crash("before_intent", i)
    old = db.receipt(rid, key) if POLICY != "checkpoint" else None
    if old and old["status"] == "done":
        trace("receipt_replay", i=i)
        return old["result"]
    if old:
        verdict = observe(EFFECT, item, CFG["observer"] == "opaque") if POLICY in {"reconcile", "contract"} else "unknown"
        trace("reconcile", i=i, verdict=verdict)
        if verdict == "unknown":
            return {"blocked": True, "reason": "uncertain_effect"}
        if verdict == "applied":
            return db.commit(rid, key, {"i": i + 1})
    elif POLICY != "checkpoint":
        db.begin_tool(rid, key)
    crash("after_intent", i)
    with EFFECT.open("a", encoding="utf-8") as f:
        f.write(canonical(record(item)) + "\n")
        f.flush()
        os.fsync(f.fileno())
    crash("after_effect", i)
    result = {"i": i + 1}
    if POLICY != "checkpoint":
        result = db.commit(rid, key, result)
    crash("after_receipt", i)
    trace("node_complete", i=i)
    return result


async def finalize(state):
    if POLICY == "contract" and not audit(EFFECT, ITEMS)["exact"]:
        return {"blocked": True, "reason": "evidence_mismatch", "reported_complete": False}
    return {"reported_complete": True}


def route(state):
    if state.get("blocked"):
        return END
    return "execute" if state["i"] < len(ITEMS) else "finalize"


async def main():
    start = time.perf_counter()
    async with AsyncSqliteSaver.from_conn_string(str(ROOT / "graph.db")) as saver:
        graph = StateGraph(State)
        graph.add_node("execute", execute)
        graph.add_node("finalize", finalize)
        graph.add_conditional_edges(START, route)
        graph.add_conditional_edges("execute", route)
        graph.add_edge("finalize", END)
        graph = graph.compile(checkpointer=saver)
        config = {"configurable": {"thread_id": rid}, "recursion_limit": 200}
        saved = await graph.aget_state(config)
        initial = None if saved.values else {"i": 0, "blocked": False, "reported_complete": False}
        # get_state after each yielded update verifies the synced checkpoint before this fault.
        async for update in graph.astream(initial, config, durability="sync", stream_mode="updates"):
            if "execute" in update and "i" in update["execute"]:
                current = await graph.aget_state(config)
                if current.values.get("i") == update["execute"]["i"]:
                    crash("after_checkpoint", current.values["i"] - 1)
        state = (await graph.aget_state(config)).values
    durable_json(ROOT / "outcome.json", {"state": state, "worker_seconds": time.perf_counter() - start})
    trace("process_complete", **state)


if __name__ == "__main__":
    asyncio.run(main())
