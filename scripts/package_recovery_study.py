"""Package audited paper, raw cases and pinned sources without abandoned drafts/caches."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import sys
import zipfile

workspace = Path(sys.argv[1]).resolve()
export = workspace / "exports"
export.mkdir(exist_ok=True)
pdf = workspace / "paper/main.pdf"
if not pdf.is_file():
    raise SystemExit("Compile and review the paper before packaging")

files = set()
for p in (workspace / "paper").rglob("*"):
    if p.is_file() and p.suffix in {".tex", ".bib", ".pdf", ".png", ".log", ".bbl"} and not p.name.startswith("_"):
        files.add(p)
paper_files = set(files)
for folder in ("verified_bench", "results", "analysis", "validation"):
    for p in (workspace / folder).rglob("*"):
        if not p.is_file() or {"__pycache__", ".ui-cache", "pre-fact-review"}.intersection(p.parts) or p.name.startswith("_"):
            continue
        if p.suffix in {".py", ".csv", ".json", ".jsonl", ".log", ".db", ".png", ".md", ".txt"}:
            files.add(p)
manifest = workspace / "runtime_under_test/source_manifest.json"
for rel, expected in json.loads(manifest.read_text())["files"].items():
    p = workspace / rel.replace("\\", "/")
    if hashlib.sha256(p.read_bytes()).hexdigest() != expected:
        raise SystemExit("Snapshot differs: " + rel)
    files.add(p)
files.add(manifest)
for name in ("README.md", "SUMMARY_ZH.md", "CLAIMS_EVIDENCE.md", "PROVENANCE_HASHES.json", "RESEARCH_SCOPE.md", "OPERATOR_REVIEW.md", "env_check.py"):
    p = workspace / name
    if p.is_file():
        files.add(p)
lock = export / "reproduction-requirements.txt"
lock.write_text("\n".join(f"{name}=={importlib.metadata.version(name)}" for name in
                ("langgraph", "langgraph-checkpoint-sqlite", "langchain-core", "numpy", "pandas", "matplotlib", "pypdf")) + "\n")
files.add(lock)
for p in (workspace / "runs").glob("*.json"):
    data = json.loads(p.read_text())
    script = data.get("script", "")
    if script.startswith(("verified_bench/", "analysis/")) and "/_" not in script:
        files.add(p)
        for suffix in (".stdout.txt", ".stderr.txt"):
            log = p.with_name(p.stem + suffix)
            if log.is_file():
                files.add(log)
inventory = {p.relative_to(workspace).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
inventory_path = export / "content-sha256.json"
inventory_path.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
files.add(inventory_path)
for name, selection in (("recovery-study-reproducibility.zip", files), ("recovery-study-manuscript.zip", paper_files)):
    with zipfile.ZipFile(export / name, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for p in sorted(selection):
            archive.write(p, p.relative_to(workspace).as_posix())
    with zipfile.ZipFile(export / name) as archive:
        assert archive.testzip() is None
    print(name, (export / name).stat().st_size, "bytes", len(selection), "files")
out = Path(__file__).resolve().parents[1] / "output" / "recovery-study"
out.mkdir(parents=True, exist_ok=True)
deliverables = {
    "paper.pdf": pdf,
    "results.csv": workspace / "results/analysis/policy_summary.csv",
    "raw-cases.csv": workspace / "results/analysis/cases_flat.csv",
    "reproducibility.zip": export / "recovery-study-reproducibility.zip",
    "manuscript.zip": export / "recovery-study-manuscript.zip",
    "validation.json": workspace / "validation/independent-raw-audit.json",
}
for name in ("README.md", "SUMMARY_ZH.md", "CLAIMS_EVIDENCE.md"):
    if (workspace / name).exists():
        deliverables[name] = workspace / name
for name, source in deliverables.items():
    shutil.copy2(source, out / name)
print("Delivery directory:", out)
