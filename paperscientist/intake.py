"""Freeze starting materials in the session before planning a reproduction or extension."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
from pathlib import Path, PureWindowsPath
import subprocess
import re
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit, urljoin, quote
from uuid import uuid4

import httpx
from pypdf import PdfReader
from . import network

MAX_PDF = 25_000_000
ARXIV = r"(?:\d{4}\.\d{4,5}|[a-z][a-z0-9.-]*/\d{7})(?:v[1-9]\d*)?"


async def public_bytes(url, limit):
    # Like the scholarly metadata clients, call only fixed HTTPS provider origins.
    # Inputs select repository refs or arXiv IDs, never a host or credentials.
    origin = urlsplit(url).netloc
    if origin not in {"arxiv.org", "raw.githubusercontent.com"}:
        raise ValueError("Unsupported intake provider")
    try:
        async with httpx.AsyncClient(
            timeout=40, follow_redirects=False, **network.client_options()
        ) as client:
            for _ in range(4):
                if urlsplit(url).scheme != "https" or urlsplit(url).netloc != origin:
                    raise ValueError("Intake provider redirected outside its origin")
                async with client.stream(
                    "GET", url, headers={"User-Agent": "PaperScientist research intake"}
                ) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get("location", ""))
                        continue
                    response.raise_for_status()
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(data) + len(chunk) > limit:
                            raise ValueError("Source exceeds the intake size limit")
                        data.extend(chunk)
                    return bytes(data)
            raise ValueError("Too many intake source redirects")
    except httpx.HTTPError as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        raise ValueError(
            f"Could not retrieve {origin}" + (f" (HTTP {status})" if status else "")
        ) from None


def inspect_git_tree(url, revision, paths):
    """Read public tree metadata at one revision, without checking out files or invoking repository code."""
    with TemporaryDirectory(prefix="ps-intake-") as tmp:
        env = {
            k: v
            for k, v in os.environ.items()
            if k
            in {
                "PATH",
                "SYSTEMROOT",
                "TMP",
                "TEMP",
                "LANG",
                "LC_ALL",
                "SSL_CERT_FILE",
                "SSL_CERT_DIR",
            }
        }
        proxy = network.client_options().get("proxy")
        if proxy:
            env["HTTPS_PROXY"] = proxy
        env.update(
            GIT_TERMINAL_PROMPT="0",
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_ALLOW_PROTOCOL="https",
        )

        def git(*args):
            try:
                return subprocess.run(
                    [
                        "git",
                        "-c",
                        "http.followRedirects=false",
                        "-c",
                        "core.hooksPath=" + os.devnull,
                        "-c",
                        "credential.helper=",
                        "-c",
                        "http.lowSpeedTime=20",
                        "-c",
                        "http.lowSpeedLimit=256",
                        *args,
                    ],
                    cwd=tmp,
                    env=env,
                    timeout=60,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    check=True,
                ).stdout
            except FileNotFoundError:
                raise ValueError(
                    "Install Git to pin a GitHub research source"
                ) from None
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                raise ValueError(
                    "Could not inspect the public GitHub repository at the requested revision"
                ) from None

        git("init", "--bare", "--template=")
        if revision != "HEAD":
            git("check-ref-format", "--allow-onelevel", revision)
        git("fetch", "--no-tags", "--depth=1", "--filter=blob:none", url, revision)
        sha = (
            git("rev-parse", "--verify", "FETCH_HEAD^{commit}").decode("ascii").strip()
        )
        names = (
            git("ls-tree", "--name-only", "-z", "FETCH_HEAD")
            .decode("utf-8", "replace")
            .split("\x00")
        )
        blobs = {}
        if paths:
            listing = git(
                "--literal-pathspecs", "ls-tree", "-z", "--full-tree", sha, "--", *paths
            )
            for entry in listing.rstrip(b"\x00").split(b"\x00") if listing else ():
                meta, name = entry.split(b"\t", 1)
                mode, kind, oid = meta.decode("ascii").split()
                if mode in {"100644", "100755"} and kind == "blob":
                    blobs[name.decode("utf-8")] = oid
            if set(blobs) != set(paths):
                raise ValueError(
                    "Every selected source must be a regular file at the pinned revision"
                )
        return sha, [name for name in names if name], blobs


async def pin_repository(url, revision, paths=()):
    match = re.fullmatch(
        r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/?", url
    )
    if not match:
        raise ValueError(
            "Supply a public GitHub repository root URL and pass its branch, tag or commit separately"
        )
    owner, repo = match.groups()
    repo = repo.removesuffix(".git")
    if owner in {".", ".."} or repo in {"", ".", ".."}:
        raise ValueError("Invalid GitHub repository name")
    if len(revision) > 200 or any(ord(c) < 32 for c in revision):
        raise ValueError("Invalid Git revision")
    canonical = f"https://github.com/{owner}/{repo}"
    revision = revision or "HEAD"
    if not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9._/-]{0,199}", revision):
        raise ValueError("Use a branch, tag or full commit SHA")
    if len(paths) > 20 or len(set(paths)) != len(paths):
        raise ValueError("Select at most 20 distinct repository files")
    for path in paths:
        if (
            len(path) > 512
            or any(
                not part
                or part.lower() in {".", "..", ".git"}
                or PureWindowsPath(part).is_reserved()
                for part in path.split("/")
            )
            or any(ch in path for ch in ("\\", ":", "\x00"))
        ):
            raise ValueError("Invalid relative repository file path")
    sha, names, blobs = await asyncio.to_thread(
        inspect_git_tree, canonical, revision, paths
    )
    likely = sorted(
        n
        for n in names
        if re.match(
            r"(?i)^(readme|licen[sc]e|requirements|environment|pyproject|package\.json|docker|configs?$|benchmarks?$|evaluations?$|experiments?$|tests?$)",
            n,
        )
    )
    return {
        "url": f"https://github.com/{owner}/{repo}",
        "requested_ref": revision,
        "commit": sha,
        "permalink": f"https://github.com/{owner}/{repo}/tree/{sha}",
        "root_entries": len(names),
        "entry_points": likely[:40],
        "source_blobs": blobs,
        "baseline_status": "source inspected; reproduction untested",
    }


def paper_info(data):
    if not data.startswith(b"%PDF-"):
        raise ValueError("The paper source did not return a PDF")
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        pages = len(reader.pages)
        title = (reader.metadata or {}).get("/Title")
    except Exception as exc:
        raise ValueError("The paper PDF is unreadable or encrypted") from exc
    if pages < 1:
        raise ValueError("The paper PDF has no pages")
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "pages": pages,
        "title": str(title or "")[:300],
    }


async def freeze_paper(store, sid, paper):
    arxiv = re.fullmatch(
        rf"https://arxiv\.org/(?:abs|pdf)/({ARXIV})(?:\.pdf)?/?", paper
    )
    if arxiv:
        source = f"https://arxiv.org/pdf/{arxiv[1]}"
        data = await public_bytes(source, MAX_PDF)
    else:
        if "://" in paper or not paper.lower().endswith(".pdf"):
            raise ValueError("Supply an arXiv abs/pdf URL or a session PDF path")
        source = store.file(sid, paper)
        if not source.is_file() or source.stat().st_size > MAX_PDF:
            raise ValueError("Session PDF is missing or exceeds 25 MB")
        data = await asyncio.to_thread(source.read_bytes)
        source = source.relative_to(store.workspace(sid)).as_posix()
    metadata = await asyncio.to_thread(paper_info, data)
    return data, {"source": source, **metadata}


def inspect_receipts(store, sid, ids):
    if len(ids) > 20 or len(set(ids)) != len(ids):
        raise ValueError("Select up to 20 distinct registered artifact IDs")
    artifacts = {item["id"]: item for item in store.artifacts(sid)}
    output = []
    for aid in ids:
        if aid not in artifacts:
            raise ValueError("Selected artifact is not registered in this session")
        item = artifacts[aid]
        filename = store.file(sid, item["path"])
        path = filename.relative_to(store.workspace(sid)).as_posix()
        expected = item["metadata"].get("sha256")
        actual = None
        if filename.is_file():
            with filename.open("rb") as f:
                actual = hashlib.file_digest(f, "sha256").hexdigest()
        status = (
            "missing"
            if not actual
            else "unchanged"
            if actual == expected
            else "changed"
        )
        output.append(
            {
                "id": aid,
                "path": path,
                "kind": item["kind"],
                "registered_sha256": expected,
                "current_sha256": actual,
                "status": status,
            }
        )
    return output


def require_writable(store, sid):
    session = store.get_session(sid)
    if not session:
        raise ValueError("Session no longer exists")
    store.session(sid, user_id=session["user_id"], project_id=session["project_id"])


async def prepare_intake(
    store,
    sid,
    objective,
    repository="",
    revision="",
    paper="",
    artifact_ids=(),
    source_paths=(),
):
    require_writable(store, sid)
    objective = objective.strip()
    if not 0 < len(objective) <= 16000 or not (repository or paper or artifact_ids):
        raise ValueError(
            "Give a research objective and at least one repository, paper or existing artifact"
        )
    if (revision or source_paths) and not repository:
        raise ValueError("A Git revision needs a repository")
    receipts = await asyncio.to_thread(inspect_receipts, store, sid, artifact_ids)
    repo = (
        await pin_repository(repository, revision, source_paths) if repository else None
    )
    raw, reference = await freeze_paper(store, sid, paper) if paper else (None, None)
    require_writable(store, sid)
    rel = "intake/" + uuid4().hex
    folder = store.file(sid, rel)
    folder.parent.mkdir(parents=True, exist_ok=True)
    if reference:
        reference["path"] = rel + "/paper.pdf"
    material = {
        "objective": objective,
        "repository": repo,
        "paper": reference,
        "prior_artifacts": receipts,
    }
    with TemporaryDirectory(dir=folder.parent) as tmp:
        bundle = Path(tmp) / "packet"
        bundle.mkdir()
        if repo and repo["source_blobs"]:
            repo["files"] = []
            total = 0
            for path, oid in repo["source_blobs"].items():
                prefix = repo["url"].replace(
                    "https://github.com/", "https://raw.githubusercontent.com/"
                )
                data = await public_bytes(
                    f"{prefix}/{repo['commit']}/{quote(path)}",
                    min(2_000_000, 12_000_000 - total),
                )
                if (
                    hashlib.sha1(
                        b"blob " + str(len(data)).encode() + b"\x00" + data
                    ).hexdigest()
                    != oid
                ):
                    raise ValueError("Selected source does not match its Git object")
                target = bundle / "repository" / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                total += len(data)
                repo["files"].append(
                    {
                        "source_path": path,
                        "workspace_path": rel + "/repository/" + path,
                        "git_blob": oid,
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
        if raw is not None:
            (bundle / "paper.pdf").write_bytes(raw)
        (bundle / "intake.json").write_text(
            json.dumps(material, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        require_writable(store, sid)
        os.rename(bundle, folder)
    artifact = store.artifact(sid, folder / "intake.json", "research_intake")
    return {**material, "artifact": artifact}
