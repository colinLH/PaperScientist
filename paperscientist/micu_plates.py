"""Produce individually reusable conceptual panels and assemble with vector typography."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory
import time
from weakref import WeakValueDictionary

from . import micu_images, plate_render

# Isolate sessions and event loops. Concurrent requests for the same local panel share a render.
_panel_locks = WeakValueDictionary()


def check_spec(spec, layout):
    panels = spec.get("panels")
    if not isinstance(panels, list) or not 2 <= len(panels) <= 6:
        raise ValueError("A framework_plate needs 2–6 conceptual panels")
    cols = spec.setdefault("columns", min(3, len(panels)))
    if type(cols) is not int or not 1 <= cols <= len(panels):
        raise ValueError("columns must be an integer between 1 and the panel count")
    size = spec.setdefault("size", [7.1, 2.45 * math.ceil(len(panels) / cols)])
    if (
        not isinstance(size, list)
        or len(size) != 2
        or not all(type(x) in (int, float) and 0.5 <= x <= 20 for x in size)
    ):
        raise ValueError(
            "size must be two positive physical dimensions in inches (0.5–20)"
        )
    ids = []
    for p in panels:
        if (
            not isinstance(p, dict)
            or not isinstance(p.get("id"), str)
            or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]{0,49}", p["id"])
        ):
            raise ValueError("Each panel needs a short alphanumeric id")
        if (
            p["id"] in ids
            or not isinstance(p.get("title"), str)
            or not p["title"].strip()
            or "\n" in p["title"]
        ):
            raise ValueError("Panels need unique IDs and one-line titles")
        ids.append(p["id"])
        if bool(p.get("asset")) == bool(p.get("prompt")):
            raise ValueError(
                "Provide exactly one workspace asset path or standalone prompt per panel"
            )
        if p.get("asset") and not isinstance(p["asset"], str):
            raise ValueError("asset must be a workspace path")
        if p.get("prompt") and (
            not isinstance(p["prompt"], str)
            or not p["prompt"].strip()
            or len(p["prompt"]) > 7000
        ):
            raise ValueError(
                "Prompt must be a standalone description of 1–7000 characters"
            )
        labels = p.get("labels", [])
        if not isinstance(labels, list) or len(labels) > 5:
            raise ValueError("Use at most five short editable labels per panel")
        for label in labels:
            if (
                not isinstance(label, dict)
                or not isinstance(label.get("text"), str)
                or not label["text"].strip()
            ):
                raise ValueError("Supply label text and normalized x/y coordinates")
            if not all(
                type(label.get(k)) in (int, float) and 0 <= label[k] <= 1
                for k in ("x", "y")
            ):
                raise ValueError(
                    "Label coordinates must be between 0 and 1, from the top left"
                )
        zoom = p.get("zoom")
        if zoom is not None:
            if (
                not isinstance(zoom, list)
                or len(zoom) != 4
                or not all(type(x) in (int, float) and 0 <= x <= 1 for x in zoom)
            ):
                raise ValueError(
                    "zoom must be [left, top, right, bottom] as fractions of the original panel image"
                )
            if zoom[0] >= zoom[2] or zoom[1] >= zoom[3]:
                raise ValueError("zoom must enclose a positive area")
    for link in spec.get("links", []):
        if (
            not isinstance(link, list)
            or len(link) != 2
            or any(x not in ids for x in link)
        ):
            raise ValueError("Each directed link is [source_id, target_id]")
        a, b = (ids.index(x) for x in link)
        if abs(a // cols - b // cols) + abs(a % cols - b % cols) != 1:
            raise ValueError("Links must join neighboring panel cells")
    font = max(7.0, float((layout or {}).get("minimum_font_pt", 7)))
    plate_render.geometry(spec, font)
    return font


def copy_local(source, target):
    if source.stat().st_size > micu_images.MAX_IMAGE_BYTES:
        raise ValueError("Local artwork exceeds size limit")
    data = source.read_bytes()
    with micu_images.normalized_raster(data) as im:
        im.save(target)
    return {"origin": "workspace", "source_sha256": hashlib.sha256(data).hexdigest()}


async def generated_part(settings, prompt, cache):
    key = hashlib.sha256(
        json.dumps([settings.image_model, prompt], ensure_ascii=False).encode()
    ).hexdigest()
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / key
    lock_key = (asyncio.get_running_loop(), dest)
    lock = _panel_locks.setdefault(lock_key, asyncio.Lock())
    async with lock:
        if not dest.exists():
            data, endpoint = await micu_images.generate(settings, prompt)
            with TemporaryDirectory(dir=cache) as tmp:
                ready = Path(tmp) / "ready"
                ready.mkdir()
                with micu_images.normalized_raster(data) as im:
                    im.save(ready / "part.png")
                record = {
                    "origin": "MicuAPI",
                    "model": settings.image_model,
                    "endpoint": endpoint,
                    "prompt": prompt,
                    "source_sha256": hashlib.sha256(data).hexdigest(),
                }
                (ready / "record.json").write_text(
                    json.dumps(record, ensure_ascii=False), encoding="utf-8"
                )
                try:
                    ready.rename(dest)
                except OSError:
                    if not (dest / "record.json").is_file():
                        raise
        return dest / "part.png", json.loads(
            (dest / "record.json").read_text(encoding="utf-8")
        )


async def create_plate(store, sid, spec, settings, plot_lock, layout, digest):
    font = check_spec(spec, layout)
    folder = store.file(sid, f"figures/plate_{time.time_ns()}")
    folder.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=folder.parent) as tmp:
        bundle = Path(tmp) / "plate"
        parts = bundle / "parts"
        parts.mkdir(parents=True)
        records = {}
        for panel in spec["panels"]:
            if panel.get("asset"):
                records[panel["id"]] = await asyncio.to_thread(
                    copy_local,
                    store.file(sid, panel["asset"]),
                    parts / (panel["id"] + ".png"),
                )
        cells = plate_render.geometry(spec, font)
        for panel, (_, _, w, h, header) in zip(spec["panels"], cells):
            if panel.get("prompt"):
                prompt = micu_images.illustration_prompt(
                    "Draw only this component as a text-free technical vignette. No panel letters, captions, "
                    "numeric result plots or inter-panel arrows; these will be typeset separately.\n"
                    + panel["prompt"],
                    (w * spec["size"][0], (h - header) * spec["size"][1]),
                )
                asset, records[panel["id"]] = await generated_part(
                    settings, prompt, store.file(sid, ".figure-cache/panels")
                )
                shutil.copyfile(asset, parts / (panel["id"] + ".png"))
        (bundle / "spec.json").write_text(
            json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        shutil.copyfile(plate_render.__file__, bundle / "render.py")
        async with plot_lock:
            await asyncio.to_thread(plate_render.render, spec, bundle, font)
        bundle.rename(folder)
    return folder, {
        "tool": "figure_forge",
        "backend": "framework_plate",
        "minimum_font_pt": font,
        "panels": records,
        "source_spec_sha256": digest,
        "provenance": "Conceptual illustration",
        "status": "Inspect each panel and its links at manuscript size",
        "publication_readiness": "not_assessed",
    }
