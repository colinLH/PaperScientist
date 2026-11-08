"""MicuAPI image generation for conceptual paper illustrations."""
from __future__ import annotations

import base64
import binascii
import io
import json
import re

import httpx
from PIL import Image, UnidentifiedImageError

from . import network

CHAT_ENDPOINT = "https://www.micuapi.ai/v1/chat/completions"
IMAGE_ENDPOINT = "https://www.micuapi.ai/v1/images/generations"
MAX_IMAGE_BYTES = 24 * 1024 * 1024


def illustration_prompt(description, size):
    if not isinstance(description, str) or not 1 <= len(description.strip()) <= 8000:
        raise ValueError("Provide a standalone illustration prompt of 1–8000 characters")
    return (
        f"Generate one original conceptual illustration for a scientific paper, composed for "
        f"a {size[0]:g} × {size[1]:g} inch panel. Return an image. "
        "Build the composition around this single message. Give the main mechanism visual priority, "
        "include only the supplied entities and relationships, use a white background, restrained color "
        "with a consistent meaning, clear contours and short direct labels only where requested. "
        "Leave breathing room at the final size. "
        "Do not invent observations, measurements, citations, axes or numerical results.\n\n"
        + description.strip()
    )


def _image_reference(message):
    # Chat-compatible services use either a content part or Markdown image in text.
    content = message.get("content")
    parts = content if isinstance(content, list) else [content]
    for item in [*(message.get("images") or []), *parts]:
        if isinstance(item, dict):
            image = item.get("image_url")
            if isinstance(image, dict):
                image = image.get("url")
            if isinstance(image, str):
                return image
            item = item.get("text")
        if isinstance(item, str):
            text = item.strip()
            match = re.search(r"!\[[^\]]*\]\(<?(https://[^\s)>]+|data:image/[^\s)>]+)>?\)", text)
            if match:
                return match.group(1)
            if text.startswith(("https://", "data:image/")) and not any(c.isspace() for c in text):
                return text
    raise ValueError("MicuAPI returned no image in the chat completion")


async def _post(client, endpoint, key, request):
    try:
        async with client.stream("POST", endpoint, headers={"Authorization": "Bearer " + key}, json=request) as response:
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > 2 * MAX_IMAGE_BYTES:
                    raise ValueError("MicuAPI image response exceeds the size limit")
            try:
                document = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError):
                document = {}
            return response.status_code, document
    except (httpx.HTTPError, UnicodeError):
        # Transport errors can include credential-bearing headers.
        raise ValueError("MicuAPI image request failed in transit; completion status is unknown") from None



async def generate(settings, prompt):
    """Post only the figure prompt. Never send an API key on image downloads."""
    key = settings.credentials.get("MICUAPI_API_KEY")
    if not key:
        raise ValueError("Set MICUAPI_API_KEY in the local .env and reload the service to generate an illustration")
    model = settings.image_model
    endpoint = CHAT_ENDPOINT
    request = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7}
    async with httpx.AsyncClient(timeout=httpx.Timeout(240, connect=20), follow_redirects=False, **network.client_options()) as client:
        status, doc = await _post(client, endpoint, key, request)
        # This model currently returns 404 "Unknown endpoint." for chat. A timeout
        # could mean a paid render is already underway; never retry ambiguous failures.
        error = doc.get("error") if isinstance(doc, dict) else None
        if status == 404 and isinstance(error, dict) and str(error.get("message", "")).lower().startswith("unknown endpoint"):
            endpoint = IMAGE_ENDPOINT
            status, doc = await _post(client, endpoint, key, {"model": model, "prompt": prompt, "n": 1})
    if status != 200:
        raise ValueError(f"MicuAPI {endpoint.split('/v1/')[1]} returned HTTP {status}; check the image token, model access and quota")
    try:
        if endpoint == CHAT_ENDPOINT:
            reference = _image_reference(doc["choices"][0]["message"])
        else:
            item = doc["data"][0]
            reference = ("data:image/png;base64," + item["b64_json"] if item.get("b64_json") else item["url"])
        if not isinstance(reference, str):
            raise TypeError
    except (KeyError, IndexError, TypeError, AttributeError):
        raise ValueError("MicuAPI returned no supported image in its response") from None
    if reference.startswith("data:image/"):
        header, sep, encoded = reference.partition(",")
        if not sep or not header.endswith(";base64"):
            raise ValueError("MicuAPI returned an invalid image data URI")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("MicuAPI returned invalid base64 image data") from None
    elif reference.startswith("https://"):
        try:
            data, _, _ = await network.fetch_public(reference, MAX_IMAGE_BYTES)
        except (OSError, ValueError, httpx.HTTPError):
            # The download URL may be signed. Do not log or persist it on failure.
            raise ValueError("The MicuAPI image download failed or used an unsafe URL") from None
    else:
        raise ValueError("MicuAPI image must use a data URI or public HTTPS URL")
    if not 0 < len(data) <= MAX_IMAGE_BYTES:
        raise ValueError("MicuAPI image is empty or exceeds the size limit")
    return data, endpoint


def export_illustration(data, size, folder):
    """Normalize pixels, strip provider metadata, and fit the PDF to the requested page."""
    from matplotlib.figure import Figure

    try:
        with Image.open(io.BytesIO(data), formats=["PNG", "JPEG", "WEBP"]) as source:
            if source.width * source.height > 20_000_000 or getattr(source, "is_animated", False):
                raise ValueError("MicuAPI image must be a single raster up to 20 megapixels")
            image = source.convert("RGBA")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("MicuAPI response did not contain a valid PNG, JPEG or WebP image") from None
    image.info.clear()
    image.save(folder / "figure.png")
    figure = Figure(figsize=size)
    axes = figure.add_axes([0, 0, 1, 1])
    axes.imshow(image, interpolation="none", aspect="equal")
    axes.set_axis_off()
    figure.savefig(folder / "figure.pdf", format="pdf", bbox_inches=None, facecolor="white")
    return {"pixels": list(image.size), "target_inches": list(size),
            "effective_dpi": round(max(image.width / size[0], image.height / size[1]), 1)}
