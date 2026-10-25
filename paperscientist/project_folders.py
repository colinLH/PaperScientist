"""Optional local source folders. Binding never moves or deletes the user's files."""
from __future__ import annotations

import os
from pathlib import Path


def validate_folder(value):
    folder = Path(str(value).strip()).expanduser()
    if not folder.is_absolute():
        raise ValueError("请输入完整的本地文件夹路径")
    try:
        folder = folder.resolve(strict=True)
        if not folder.is_dir():
            raise ValueError("请选择文件夹，不能选择文件")
        with os.scandir(folder):
            pass
    except OSError as exc:
        raise ValueError("文件夹不存在或无法访问，请重新选择") from exc
    return str(folder)


def browse_folders(path="", offset=0):
    """List one level, with bounded pages; never load file contents or recurse."""
    folder = Path(validate_folder(path or str(Path.home())))
    roots = ([str(Path(f"{c}:/")) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if Path(f"{c}:/").is_dir()]
             if os.name == "nt" else ["/"])
    rows, count = [], 0
    with os.scandir(folder) as entries:
        for entry in entries:
            try:
                if not entry.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            if count >= offset and len(rows) < 100:
                rows.append({"name": entry.name, "path": str(folder / entry.name)})
            count += 1
            if count > offset + 100:
                break
    return {"path": str(folder), "parent": str(folder.parent) if folder.parent != folder else None,
            "roots": roots, "folders": sorted(rows, key=lambda r: r["name"].casefold()),
            "next_offset": offset + 100 if count > offset + 100 else None}
