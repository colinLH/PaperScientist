from __future__ import annotations

import asyncio
import ipaddress
import socket
import os
from urllib.parse import urljoin, urlparse

import httpx


def client_options():
    """Honor the configured transport proxy without importing ambient credentials."""
    proxy = os.environ.get("PS_HTTP_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if proxy:
        parsed = urlparse(proxy)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Research proxy must be HTTP(S) without embedded credentials")
    return {"trust_env": False, **({"proxy": proxy} if proxy else {})}


async def public_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only public HTTP(S) URLs without embedded credentials are allowed")
    addresses = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("Private, loopback and reserved network addresses are not allowed")


async def fetch_public(url, max_bytes=12_000_000):
    """Validate each redirect, bound downloads and disable ambient proxy credentials."""
    async with httpx.AsyncClient(timeout=40, follow_redirects=False, **client_options()) as client:
        for _ in range(6):
            await public_url(url)
            async with client.stream("GET", url, headers={"User-Agent": "PaperScientist/0.2 research assistant"}) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers["location"])
                    continue
                response.raise_for_status()
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("Download exceeds size limit")
                    chunks.append(chunk)
                return b"".join(chunks), response.headers.get("content-type", ""), url
        raise ValueError("Too many redirects")


async def search_papers(query, provider="openalex", limit=8, year_from=None, year_to=None, api_key=None):
    from defusedxml import ElementTree
    limit = max(1, min(limit, 25))
    async with httpx.AsyncClient(timeout=40, **client_options()) as client:
        if provider == "arxiv":
            response = await client.get("https://export.arxiv.org/api/query", params={
                "search_query": query if any(p in query for p in ("all:", "ti:", "au:", "cat:")) else f"all:{query}",
                "start": 0, "max_results": limit, "sortBy": "relevance",
            })
            response.raise_for_status()
            tree = ElementTree.fromstring(response.content)
            ns = {"a": "http://www.w3.org/2005/Atom"}
            result = []
            for e in tree.findall("a:entry", ns):
                year = int(e.findtext("a:published", "0000", ns)[:4])
                if (year_from and year < year_from) or (year_to and year > year_to):
                    continue
                url = e.findtext("a:id", "", ns)
                result.append({"title": " ".join(e.findtext("a:title", "", ns).split()), "year": year,
                    "authors": [a.findtext("a:name", "", ns) for a in e.findall("a:author", ns)],
                    "abstract": " ".join(e.findtext("a:summary", "", ns).split()),
                    "url": url, "pdf_url": next((x.attrib["href"] for x in e.findall("a:link", ns) if x.attrib.get("title") == "pdf"), ""),
                    "provider": "arxiv", "venue": "arXiv (preprint; peer review not verified)"})
            return result
        if provider == "crossref":
            params = {"query": query, "rows": limit}
            filters = []
            if year_from:
                filters.append(f"from-pub-date:{year_from}-01-01")
            if year_to:
                filters.append(f"until-pub-date:{year_to}-12-31")
            if filters:
                params["filter"] = ",".join(filters)
            response = await client.get("https://api.crossref.org/works", params=params)
            response.raise_for_status()
            return [{"title": (p.get("title") or [""])[0], "doi": p.get("DOI", ""), "url": p.get("URL", ""),
                     "authors": [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in p.get("author", [])],
                     "year": (p.get("published", {}).get("date-parts") or [[None]])[0][0],
                     "venue": (p.get("container-title") or [""])[0], "provider": "crossref"}
                    for p in response.json()["message"]["items"]]
        if provider != "openalex":
            raise ValueError("provider must be openalex, arxiv or crossref")
        params = {"search": query, "per-page": limit}
        filters = []
        if year_from:
            filters.append(f"from_publication_date:{year_from}-01-01")
        if year_to:
            filters.append(f"to_publication_date:{year_to}-12-31")
        if filters:
            params["filter"] = ",".join(filters)
        response = await client.get("https://api.openalex.org/works", params=params,
                                    headers={"Authorization": "Bearer " + api_key} if api_key else {})
        response.raise_for_status()
        result = []
        for p in response.json().get("results", []):
            location = p.get("primary_location") or {}
            index = p.get("abstract_inverted_index") or {}
            words = {pos: word for word, positions in index.items() for pos in positions}
            result.append({"title": p.get("title", ""), "year": p.get("publication_year"),
                "doi": (p.get("doi") or "").removeprefix("https://doi.org/"),
                "url": location.get("landing_page_url") or p.get("id", ""),
                "pdf_url": location.get("pdf_url") or "", "abstract": " ".join(words[i] for i in sorted(words)),
                "authors": [a["author"]["display_name"] for a in p.get("authorships", [])],
                "venue": (location.get("source") or {}).get("display_name", ""),
                "cited_by_count": p.get("cited_by_count"), "provider": "openalex"})
        return result
