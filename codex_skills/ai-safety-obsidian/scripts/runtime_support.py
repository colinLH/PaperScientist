"""Explicit, portable runtime configuration and nonblocking process locks."""
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from zoneinfo import ZoneInfo


def load_config(path=None):
    value = path or os.environ.get("AI_SAFETY_OBSIDIAN_CONFIG")
    if not value:
        raise ValueError("Supply --config /absolute/path/config.json; run workflow.py init first")
    file = Path(value).expanduser().resolve()
    config = json.loads(file.read_text(encoding="utf-8"))
    validate_config(config)
    return config


def validate_config(config):
    for key in ("vault_root", "workspace"):
        if not Path(config[key]).is_absolute():
            raise ValueError(key + " must be an absolute path")
    prefix = config["prefix"]
    if not prefix or prefix in {".", ".."} or re.search(r'[\\/:*?"<>|\x00-\x1f]', prefix):
        raise ValueError("prefix must be one valid directory name")
    vault = Path(config["vault_root"]).resolve()
    if not (vault / prefix).resolve().is_relative_to(vault):
        raise ValueError("Knowledge directory escapes the vault")
    if Path(config["workspace"]).resolve().is_relative_to(vault):
        raise ValueError("Keep runtime workspace outside the Obsidian vault")
    ZoneInfo(config["timezone"])
    if type(config["papers_per_day"]) is not int or config["papers_per_day"] < 1:
        raise ValueError("papers_per_day must be a positive integer")
    for key in ("collect_at", "sync_at"):
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", config[key]):
            raise ValueError(key + " must be HH:MM")
    site = config.get("site", {})
    if site.get("enabled") and (not site.get("project_id") or not site.get("url")):
        raise ValueError("Enabled Sites publishing requires project_id and url")
    return config


@contextmanager
def file_lock(path):
    """OS-owned lock: crashes release it; concurrent jobs fail without stealing it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            if path.stat().st_size == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)
