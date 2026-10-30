#!/usr/bin/env python3
"""Build a reproducible, source-only Codex skill archive from an explicit manifest."""
import argparse
import hashlib
from pathlib import Path
import zipfile

FILES = (
    "SKILL.md", "README.md", "agents/openai.yaml", "assets/EXPORT_README.md",
    "references/setup.md", "references/scheduling.md", "references/collector.md",
    "references/graph.md", "references/publishing.md", "scripts/workflow.py",
    "scripts/runtime_support.py", "scripts/graph_sync.py", "scripts/obsidian_sync.py",
    "scripts/requirements.txt", "scripts/test_workflow.py",
)


def package(source, destination):
    source = source.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(FILES):
            path = source / name
            if not path.is_file() or path.is_symlink():
                raise ValueError("Missing or linked package member: " + name)
            info = zipfile.ZipInfo("ai-safety-obsidian/" + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(destination.suffix + ".sha256").write_text(checksum + "  " + destination.name + "\n", encoding="utf-8")
    return checksum


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    repo = Path(__file__).resolve().parents[1]
    parser.add_argument("--source", type=Path, default=repo / "codex_skills/ai-safety-obsidian")
    parser.add_argument("--output", type=Path, default=repo / "codex_skills/packages/ai-safety-obsidian.skill")
    args = parser.parse_args()
    print(package(args.source, args.output))
