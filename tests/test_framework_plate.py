import asyncio
import io
import json
from pathlib import Path
from xml.etree import ElementTree

from PIL import Image
import pytest

from paperscientist import figure_forge, micu_images
from paperscientist.config import Settings
from paperscientist.store import Store


def test_failed_plate_reuses_successful_parts_and_keeps_editable_zoom(
    tmp_path, monkeypatch
):
    store = Store(tmp_path)
    sid = "author"
    store.session(sid)
    spec = {
        "type": "framework_plate",
        "columns": 2,
        "size": [5.5, 2.7],
        "links": [["a", "b"]],
        "panels": [
            {
                "id": "a",
                "title": "Message",
                "prompt": "A tiny amber envelope.",
                "zoom": [0.2, 0.3, 0.65, 0.55],
            },
            {
                "id": "b",
                "title": "Mailbox",
                "prompt": "An empty green mailbox.",
                "labels": [{"text": "Gate", "x": 0.5, "y": 0.7}],
            },
        ],
    }
    store.file(sid, "spec.json").write_text(json.dumps(spec))
    data = io.BytesIO()
    Image.new("RGB", (300, 180), "ivory").save(data, format="PNG")
    calls = []

    async def micu(settings, prompt):
        calls.append(prompt)
        if len(calls) == 2:
            raise ValueError("provider offline")
        return data.getvalue(), micu_images.IMAGE_ENDPOINT

    monkeypatch.setattr(micu_images, "generate", micu)

    async def run():
        lock = asyncio.Lock()
        with pytest.raises(ValueError, match="provider offline"):
            await figure_forge.create_agent_figure(
                store, sid, "spec.json", "paper mechanism", Settings(), lock
            )
        assert not store.artifacts(sid)
        return await figure_forge.create_agent_figure(
            store, sid, "spec.json", "paper mechanism", Settings(), lock
        )

    result = asyncio.run(run())
    assert len(calls) == 3 and calls[0] != calls[1] == calls[2]
    root = Path(store.file(sid, result["directory"]))
    svg = ElementTree.parse(root / "figure.svg")
    ns = {"s": "http://www.w3.org/2000/svg"}
    assert (
        len(svg.findall(".//s:image", ns)) == 3
    )  # Two illustrations plus an actual zoomed crop.
    assert "Gate" in [x.text for x in svg.findall(".//s:text", ns)]
    assert result["contract"]["panels"]["b"]["model"] == Settings().image_model
    assert all(
        (root / name).is_file()
        for name in [
            "parts/a.png",
            "parts/b.png",
            "render.py",
            "figure.pdf",
            "figure.png",
        ]
    )


def test_plate_preflights_assets_before_sending_paid_prompts(tmp_path, monkeypatch):
    store = Store(tmp_path)
    store.session("s")
    spec = {
        "type": "framework_plate",
        "panels": [
            {"id": "first", "title": "Draft", "prompt": "An envelope"},
            {"id": "second", "title": "Result", "asset": "../outside.png"},
        ],
    }
    store.file("s", "s.json").write_text(json.dumps(spec))

    async def unexpected_request(*args):
        pytest.fail("local assets should be checked first")

    monkeypatch.setattr(micu_images, "generate", unexpected_request)
    with pytest.raises(ValueError, match="inside the session workspace"):
        asyncio.run(
            figure_forge.create_agent_figure(
                store, "s", "s.json", "", Settings(), asyncio.Lock()
            )
        )
