"""Restore pinned project skills without running upstream installers, hooks or scripts.

python scripts/install_research_skills.py          # install missing packages/resources
python scripts/install_research_skills.py --check  # verify recorded package hashes offline
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "docs/video-skills.lock.json"


def package_name(path):
    return "sciplot-figure-skill" if path == "." else PurePosixPath(path).name


def tree_hash(root):
    digest = hashlib.sha256()
    for file in sorted(root.rglob("*")):
        if file.is_file() and "__pycache__" not in file.parts:
            if not file.resolve().is_relative_to(root.resolve()):
                raise ValueError(f"Symlink escape: {file}")
            digest.update(file.relative_to(root).as_posix().encode())
            digest.update(b"\0")
            digest.update(hashlib.sha256(file.read_bytes()).digest())
    return digest.hexdigest()


def download(url, target, limit=400_000_000):
    req = urllib.request.Request(url, headers={"User-Agent": "PaperScientist-pinned-skills/1"})
    with urllib.request.urlopen(req, timeout=120) as response, target.open("wb") as out:
        total = 0
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > limit:
                raise ValueError("Download exceeds size limit")
            out.write(chunk)


def extract_selected(archive, prefix, target):
    """Extract only one package, rejecting traversal, links and zip bombs."""
    with zipfile.ZipFile(archive) as z:
        top = z.namelist()[0].split("/")[0] + "/"
        selection = top + (prefix.rstrip("/") + "/" if prefix != "." else "")
        members = [i for i in z.infolist() if i.filename.startswith(selection) and not i.is_dir()]
        if len(members) > 12000 or sum(i.file_size for i in members) > 500_000_000:
            raise ValueError("Expanded package exceeds limit")
        for info in members:
            relative = PurePosixPath(info.filename[len(selection):])
            if relative.is_absolute() or ".." in relative.parts or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("Unsafe archive member")
            path = target.joinpath(*relative.parts)
            if not path.resolve().is_relative_to(target.resolve()):
                raise ValueError("Archive path escapes destination")
            path.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, path.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def install(source, check=False):
    dest = ROOT / source["local_dir"]
    packages = [(path, dest / package_name(path)) for path in source["skill_paths"]]
    missing = [(path, target) for path, target in packages if not (target / "SKILL.md").is_file()]
    extras = [p for p in source["source_paths"] if not (dest / "_source" / p).is_file()]
    if check:
        if missing or extras or not (dest / ".source.json").is_file():
            raise ValueError(f"{source['id']}: missing packages/resources")
    else:
        dest.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="psskills-") as temporary:
            temp = Path(temporary)
            archive = temp / "source.zip"
            if missing or len(extras) > 20:
                download(f"https://codeload.github.com/{source['repo']}/zip/{source['commit']}", archive)
            for path, target in missing:
                if target.exists():
                    raise ValueError(f"Incomplete destination exists: {target}; inspect it before retrying")
                staging = temp / package_name(path)
                extract_selected(archive, path, staging)
                if not (staging / "SKILL.md").is_file():
                    raise ValueError(f"Missing SKILL.md for {path}")
                shutil.copytree(staging, target)
            for path in extras:
                target = dest / "_source" / path
                target.parent.mkdir(parents=True, exist_ok=True)
                if archive.exists():
                    with zipfile.ZipFile(archive) as z:
                        top = z.namelist()[0].split("/")[0]
                        target.write_bytes(z.read(f"{top}/{path}"))
                else:
                    download(f"https://raw.githubusercontent.com/{source['repo']}/{source['commit']}/{path}", target, 5_000_000)
        metadata = {k: source[k] for k in ("id", "repo", "url", "commit", "license", "topics")}
        (dest / ".source.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    hashes = {package_name(path): tree_hash(target) for path, target in packages}
    hashes["_source"] = tree_hash(dest / "_source")
    expected = source.get("package_hashes")
    if expected and expected != hashes:
        raise ValueError(f"{source['id']}: package hash mismatch; local edits or corrupt download")
    if check and not expected:
        raise ValueError(f"{source['id']}: no recorded checksums")
    return hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--record-hashes", action="store_true", help="Seal an intentionally reviewed initial download")
    parser.add_argument("--source", help="Optional source ID")
    args = parser.parse_args()
    manifest = json.loads(LOCK.read_text(encoding="utf-8"))
    chosen = [s for s in manifest["sources"] if not args.source or s["id"] == args.source]
    if not chosen:
        parser.error("Unknown source")
    for source in chosen:
        hashes = install(source, args.check)
        if args.record_hashes:
            source["package_hashes"] = hashes
        print(f"{source['id']}: {len(source['skill_paths'])} skill packages verified", flush=True)
    if args.record_hashes:
        LOCK.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
