"""Explicit, idempotent import of legacy chat JSON; source files remain untouched."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

from .config import ROOT, Settings
from .store import Store


def import_chats(store, source, project_id="legacy", apply=False):
    report = {"files":0,"turns":0,"imported":0,"skipped":0,"errors":[]}
    for path in sorted(Path(source).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            turns = data.get("turns",[])
            if not isinstance(turns,list):
                raise ValueError("turns must be a list")
            sid = "legacy_"+hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:24]
            report["files"] += 1
            report["turns"] += len(turns)
            if not apply:
                continue
            store.session(sid,project_id=project_id)
            known = {e["data"].get("turn_hash") for e in store.events(sid,100000) if e["kind"]=="legacy_import"}
            for index,turn in enumerate(turns):
                digest = hashlib.sha256((str(index)+json.dumps(turn,sort_keys=True,ensure_ascii=False)).encode()).hexdigest()
                if digest in known:
                    report["skipped"] += 1
                    continue
                user, answer = turn.get("user",""),turn.get("assistant","")
                if not isinstance(user,str) or not isinstance(answer,str):
                    raise ValueError("Legacy turn content must be text")
                if user:
                    store.append(sid,HumanMessage(content=user))
                if answer:
                    store.append(sid,AIMessage(content=answer))
                store.event(sid,"legacy_import",{"source":str(path.resolve()),"turn":index,"turn_hash":digest})
                report["imported"] += 1
        except (ValueError,OSError,TypeError) as exc:
            report["errors"].append({"file":path.name,"error":str(exc)})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,default=ROOT/"web"/"chat_sessions")
    parser.add_argument("--project",default="legacy")
    parser.add_argument("--apply",action="store_true",help="Import; default only reports available legacy turns")
    args = parser.parse_args()
    print(json.dumps(import_chats(Store(Settings.load().data_dir),args.source,args.project,args.apply),ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
