"""Deterministic workload and an independent, strict artifact oracle."""
import hashlib
import json
import os
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def plan(n, seed):
    # Synthetic records, not real scientific discoveries or LLM decisions.
    return [{"id": f"op-{i}", "value": digest([seed, i, "cpu-record"])} for i in range(n)]


def record(item):
    return {**item, "sha256": digest(item)}


def durable_json(path, data):
    path = Path(path)
    with path.with_suffix(".tmp").open("w", encoding="utf-8") as f:
        json.dump(data, f, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(path.with_suffix(".tmp"), path)


def read_records(path):
    # Invalid/truncated evidence must not be silently discarded.
    rows, valid = [], True
    if not path.exists():
        return rows, False
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                valid = False
                continue
            if set(row) != {"id", "value", "sha256"}:
                valid = False
                continue
            if row["sha256"] != digest({k: row[k] for k in ("id", "value")}):
                valid = False
            rows.append(row)
        return rows, valid
    except (ValueError, OSError, UnicodeError, TypeError):
        return rows, False


def observe(path, expected, opaque=False):
    if opaque:
        return "unknown"
    rows, valid = read_records(path)
    matches = [r for r in rows if r["id"] == expected["id"]]
    if not valid or len(matches) > 1:
        return "unknown"
    if not matches:
        # Only valid for this exclusive single-writer, readable local effect store.
        return "absent"
    return "applied" if matches == [record(expected)] else "unknown"


def audit(path, expected):
    rows, valid = read_records(path)
    by_id = {item["id"]: [r for r in rows if r["id"] == item["id"]] for item in expected}
    duplicates = sum(max(0, len(values) - 1) for values in by_id.values())
    missing = sum(not values for values in by_id.values())
    wrong = sum(bool(values) and any(r != record(item) for r in values)
                for item in expected for values in [by_id[item["id"]]])
    exact = valid and rows == [record(item) for item in expected]
    return {"exact": exact, "valid_encoding": valid, "duplicate_effects": duplicates,
            "missing_effects": missing, "wrong_effects": wrong, "observed_records": len(rows)}
