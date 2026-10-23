"""Re-run the matrix in a NEW directory, preserving the delivered evidence."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

source = Path(__file__).resolve().parents[1]
target = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else source / "replay"
target.mkdir(parents=True, exist_ok=False)
for folder in ("verified_bench", "analysis"):
    (target / folder).mkdir()
    for path in (source / folder).glob("*.py"):
        if not path.name.startswith("_"):
            shutil.copy2(path, target / folder / path.name)
manifest = source / "runtime_under_test/source_manifest.json"
for relative in json.loads(manifest.read_text())["files"]:
    relative = Path(relative.replace("\\", "/"))
    dest = target / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / relative, dest)
shutil.copy2(manifest, target / "runtime_under_test/source_manifest.json")
for n in (8, 24, 64):
    subprocess.run([sys.executable, str(target / f"verified_bench/run_{n}.py")], check=True, cwd=target)
subprocess.run([sys.executable, str(target / "verified_bench/verify_raw.py"), str(target)], check=True, cwd=target)
subprocess.run([sys.executable, str(target / "analysis/aggregate.py")], check=True, cwd=target)
print("New raw results and independent audit:", target)
