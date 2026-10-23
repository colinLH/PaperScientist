"""Run isolated real processes; retain all databases, traces and raw outcomes."""
import concurrent.futures
import csv
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

from common import audit, durable_json, plan

HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE.parent / "runtime_under_test"
if not SNAPSHOT.exists():
    SNAPSHOT = HERE.parents[1]  # repo development invocation
sys.path.insert(0, str(SNAPSHOT))
from paperscientist.store import Store
from paperscientist.run_store import RunStore

POLICIES = ["checkpoint", "receipt", "reconcile", "contract"]
POINTS = ["none", "before_intent", "after_intent", "after_effect", "after_receipt", "after_checkpoint"]


def scenarios(n):
    for policy in POLICIES:
        yield dict(policy=policy, n=n, seed=n, point="none", target=0, observer="readable", perturbation="none")
        for point in POINTS[1:]:
            for target in (0, n // 2, n - 1):
                yield dict(policy=policy, n=n, seed=n + target, point=point, target=target, observer="readable", perturbation="none")
        for observer, perturbation, point in [("opaque", "none", "after_effect"), ("readable", "torn_record", "after_effect"), ("readable", "tamper_value", "after_receipt")]:
            yield dict(policy=policy, n=n, seed=n, point=point, target=n // 2, observer=observer, perturbation=perturbation)


def one(config, output):
    cid = "_".join(str(config[k]) for k in ("policy", "n", "point", "target", "observer", "perturbation"))
    root = output / "cases" / cid
    root.mkdir(parents=True, exist_ok=False)  # never erase prior runs
    config = {**config, "snapshot": str(SNAPSHOT.resolve())}
    durable_json(root / "config.json", config)
    (root / "effects.jsonl").write_text("")
    store = Store(root / "metadata")
    store.session("s1")
    run = RunStore(store).create("s1", "deterministic fault-injection fixture", {"fixture": True})
    durable_json(root / "identity.json", {"run_id": run["id"]})
    codes, elapsed = [], []
    for lifetime in range(3):
        start = time.perf_counter()
        with (root / f"lifetime_{lifetime}.log").open("wb") as log:
            child = subprocess.run([sys.executable, str(HERE / "worker.py"), str(root)], stdout=log, stderr=subprocess.STDOUT,
                                   timeout=70, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        elapsed.append(time.perf_counter() - start)
        codes.append(child.returncode)
        if child.returncode == 0:
            break
        if child.returncode != 73:
            raise RuntimeError(f"{cid} failed: see {root}")
        if config["perturbation"] == "torn_record":
            with (root / "effects.jsonl").open("ab") as f:
                f.write(b'{"torn":')
                f.flush(); os.fsync(f.fileno())
        elif config["perturbation"] == "tamper_value":
            # Keep valid JSON but invalidate content hash after a committed receipt.
            p = root / "effects.jsonl"
            text = p.read_text().replace('"value":"', '"value":"changed-', 1)
            p.write_text(text)
    outcome = json.loads((root / "outcome.json").read_text())
    expected = plan(config["n"], config["seed"])
    measured = audit(root / "effects.jsonl", expected)
    reported = bool(outcome["state"].get("reported_complete"))
    row = {"case_id": cid, **{k: v for k, v in config.items() if k != "snapshot"}, **measured,
           "reported_complete": reported, "verified_success": reported and measured["exact"],
           "false_completion": reported and not measured["exact"], "blocked": bool(outcome["state"].get("blocked")),
           "reason": outcome["state"].get("reason", ""), "crash_observed": 73 in codes,
           "lifetimes": len(codes), "total_seconds": sum(elapsed), "resume_seconds": elapsed[-1] if len(codes) > 1 else 0,
           "worker_seconds": outcome["worker_seconds"], "exit_codes": json.dumps(codes)}
    durable_json(root / "measured.json", row)
    return row


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    output = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else HERE.parent / "results" / f"verified_{n}"
    output.mkdir(parents=True, exist_ok=True)
    configs = list(scenarios(n))
    start = time.perf_counter()
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(one, cfg, output) for cfg in configs]
        for future in concurrent.futures.as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda x: x["case_id"])
    with (output / "raw.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    durable_json(output / "environment.json", {"python": sys.version, "platform": platform.platform(), "cpu": platform.processor(),
        "logical_cpus": os.cpu_count(), "workers": 4, "elapsed_seconds": time.perf_counter()-start,
        "packages": {k: importlib.metadata.version(k) for k in ("langgraph", "langgraph-checkpoint-sqlite", "langchain-core")}})
    print(json.dumps({"rows": len(rows), "output": str(output), "seconds": time.perf_counter()-start}))


if __name__ == "__main__":
    main()
