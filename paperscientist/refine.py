"""Offline evidence-based history mining. Dry-run by default; never rewrites raw history."""
from __future__ import annotations

import argparse
import asyncio
import json

from langchain_core.messages import HumanMessage, SystemMessage

from .config import Settings, create_model
from .memory import EXTRACTION_PROMPT, MemoryManager, json_object, text_content
from .store import Store, dumps


async def refine_history(store, session_id, model, apply=False, max_messages=20):
    session = store.get_session(session_id)
    if not session:
        raise ValueError("Session not found")
    if session.get("parent_id"):
        raise ValueError("Only actual user sessions may refine personal memory")
    manager = MemoryManager(store, session)
    messages = [(mid, text_content(m)) for mid, m in store.history(session_id) if m.type == "human"][-max_messages:]
    report = {"session_id": session_id, "applied": apply, "proposals": [], "rejected": 0}
    # Bounded batches avoid turning history mining into another unbounded context.
    for mid, content in messages:
        answer = await model.ainvoke([SystemMessage(content=EXTRACTION_PROMPT), HumanMessage(content=dumps({
            "actual_user_input": content[:12000], "existing_memory": store.injected_memory(session)}))])
        data = json_object(text_content(answer))
        for update in data.get("updates", [])[:3]:
            kind, text, quote = update.get("kind"), update.get("content"), update.get("evidence_quote", "")
            if kind not in {"user_profile", "project_memory"} or not isinstance(text, str) or len(text) > 400 or len(quote) < 3 or quote not in content:
                report["rejected"] += 1
                continue
            old = store.memories(kind, store.memory_owner(kind, session))
            if any(m["content"].get("text") == text for m in old) or any(p["content"] == text and p["kind"] == kind for p in report["proposals"]):
                continue
            proposal = {"kind": kind, "content": text, "source_message_id": mid, "evidence_quote": quote}
            if apply:
                proposal["memory"] = manager.remember(kind, text, quote)
            report["proposals"].append(proposal)
    if apply:
        store.event(session_id, "history_refined", {"count": len(report["proposals"]), "rejected": report["rejected"]})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_id")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--max-messages", type=int, default=20)
    args = parser.parse_args()
    settings = Settings.load()
    result = asyncio.run(refine_history(Store(settings.data_dir), args.session_id, create_model(settings),
                                      args.apply, min(max(1, args.max_messages), 100)))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
