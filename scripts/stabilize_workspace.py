"""One-time migration of the live local workspace, preserving the original as a backup."""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import psutil

root = Path(__file__).resolve().parents[1]
processes = [p for p in psutil.process_iter(["cmdline"]) if p.info["cmdline"] and "uvicorn" in p.info["cmdline"] and "web.app:app" in p.info["cmdline"] and "8888" in p.info["cmdline"]]
if len(processes) != 1:
    raise SystemExit("Expected exactly one PaperScientist server on 8888")
process = processes[0]
env = os.environ.copy()
old_env = process.environ()
for key in ("PS_MODEL", "PS_ALLOW_EXECUTION", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "DEEPSEEK_API_BASE"):
    if key in old_env:
        env[key] = old_env[key]
source = Path(old_env.get("PS_DATA_DIR", root / ".paperscientist")).resolve()
target = (root / ".paperscientist-workspace").resolve()
if not source.is_relative_to(root) or not target.is_relative_to(root):
    raise SystemExit("Unexpected workspace location")
if source != target and target.exists():
    raise SystemExit("Target exists; refusing to overwrite")
cmd = process.cmdline()
process.terminate()
process.wait(timeout=20)
if source != target:
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("*.db", "*.db-wal", "*.db-shm"))
    for path in source.glob("*.db"):
        with sqlite3.connect(path) as src, sqlite3.connect(target / path.name) as dest:
            src.backup(dest)
    # Artifact paths are absolute in the registry; only relocate this exact workspace prefix.
    with sqlite3.connect(target / "research.db") as db:
        for aid, path in db.execute("SELECT id,path FROM artifacts").fetchall():
            old = Path(path).resolve()
            if old.is_relative_to(source):
                db.execute("UPDATE artifacts SET path=? WHERE id=?", (str(target / old.relative_to(source)), aid))
(root / "paperscientist.local.json").write_text(json.dumps({"PS_DATA_DIR": ".paperscientist-workspace", "PS_MODEL": env.get("PS_MODEL", "deepseek:deepseek-chat")}, indent=2), encoding="utf-8")
env["PS_DATA_DIR"] = str(target)
with (root / ".test-output/workspace-live.stdout.log").open("ab") as out, (root / ".test-output/workspace-live.stderr.log").open("ab") as err:
    child = subprocess.Popen(cmd, cwd=root, env=env, stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
with sqlite3.connect(target / "research.db") as db:
    count = db.execute("SELECT count(*) FROM sessions").fetchone()[0]
print(json.dumps({"pid": child.pid, "source_backup": str(source), "persistent_workspace": str(target), "sessions": count}))
