"""Independent reader: does not import the benchmark's observer or audit functions."""
import collections
import csv
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
errors, checked, rows = [], 0, []
for csv_path in sorted(root.glob("results/verified_*/raw.csv")):
    for row in csv.DictReader(csv_path.open(encoding="utf-8")):
        case = csv_path.parent / "cases" / row["case_id"]
        cfg = json.loads((case / "config.json").read_text())
        expected = []
        for i in range(cfg["n"]):
            payload = hashlib.sha256(json.dumps([cfg["seed"], i, "cpu-record"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            item = {"id": f"op-{i}", "value": payload}
            item["sha256"] = hashlib.sha256(json.dumps(item, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            expected.append(item)
        actual, valid = [], True
        for line in (case / "effects.jsonl").read_text().splitlines():
            try:
                obj = json.loads(line)
                assert set(obj) == {"id", "value", "sha256"}
                actual.append(obj)
                payload = {k: obj[k] for k in ("id", "value")}
                valid &= obj["sha256"] == hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            except (ValueError, AssertionError, TypeError):
                valid = False
        exact = actual == expected and valid
        outcome = json.loads((case / "outcome.json").read_text())["state"]
        complete = outcome.get("reported_complete", False)
        computed = {"exact": exact, "verified_success": complete and exact,
                    "false_completion": complete and not exact, "blocked": outcome.get("blocked", False)}
        for key, value in computed.items():
            if str(value) != row[key]:
                errors.append(f"{row['case_id']}:{key}")
        counts = collections.Counter(x["id"] for x in actual)
        duplicates = sum(max(0, counts[x["id"]]-1) for x in expected)
        if duplicates != int(row["duplicate_effects"]):
            errors.append(row["case_id"] + ":duplicates")
        trace = [json.loads(x) for x in (case / "trace.jsonl").read_text().splitlines()]
        deaths = [x for x in trace if x["event"] == "hard_exit"]
        if len(deaths) != (cfg["point"] != "none"):
            errors.append(row["case_id"] + ":fault_not_injected")
        if deaths and deaths[0]["pid"] == trace[-1]["pid"]:
            errors.append(row["case_id"] + ":no_new_process")
        rows.append(row)
        checked += 1
counts = {p: {"total": sum(r["policy"] == p for r in rows),
              **{k: sum(r["policy"] == p and r[k] == "True" for r in rows)
                 for k in ("verified_success", "false_completion", "blocked")}}
          for p in ("checkpoint", "receipt", "reconcile", "contract")}
report = {"checked_cases": checked, "errors": errors, "independent_reader": True, "all_designed_cases_not_population_rates": counts}
target = root / "validation" / "independent-raw-audit.json"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report))
if errors or checked != 228:
    raise SystemExit(1)
