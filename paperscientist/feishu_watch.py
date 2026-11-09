"""Explicit, read-only CLI subscription for one durable run; isolated from the research service."""

from __future__ import annotations

import base64
from contextlib import closing
import hashlib
import hmac
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import quote, urlsplit

import httpx
from dotenv import dotenv_values


LABELS = {
    "waiting_input": "需要你在本地工作台回答问题",
    "paused": "已暂停",
    "stopped": "已停止",
    "error": "发生错误，请在本地工作台检查",
    "completed": "已完成",
}


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _destination(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc not in {"open.feishu.cn", "open.larksuite.com"}
        or not re.fullmatch(r"/open-apis/bot/v2/hook/[A-Za-z0-9_-]+", parsed.path)
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "PS_FEISHU_WEBHOOK must be an official HTTPS custom-bot webhook"
        )
    return url


def _post(client, url, secret, text):
    body = {"msg_type": "text", "content": {"text": text}}
    if secret:
        timestamp = str(int(time.time()))
        key = (timestamp + "\n" + secret).encode()
        body.update(
            timestamp=timestamp,
            sign=base64.b64encode(hmac.digest(key, b"", "sha256")).decode(),
        )
    try:
        response = client.post(url, json=body, follow_redirects=False)
        data = response.json() if response.is_success else {}
        code = (
            data.get("code", data.get("StatusCode")) if isinstance(data, dict) else None
        )
        if response.is_success and type(code) is int and code == 0:
            return
    except (httpx.HTTPError, ValueError):
        pass
    # Transport error strings may contain the entire credential-bearing webhook URL.
    raise ValueError(
        "Feishu delivery was rejected or unconfirmed. Check the local webhook configuration."
    )


def watch(
    client,
    run_id,
    *,
    once=False,
    disable=False,
    settings=None,
    state_path=None,
    transport=None,
    poll_seconds=8,
):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", run_id):
        raise ValueError("Invalid research run ID")
    scope = digest(str(client.base_url).rstrip("/") + "\n" + run_id)
    ref = scope[:12]
    state = (
        Path(state_path)
        if state_path
        else Path.home() / ".paperscientist" / "feishu-watches.sqlite"
    )
    state.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with closing(sqlite3.connect(state, timeout=10)) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS subscriptions (scope TEXT PRIMARY KEY, enabled INTEGER, generation INTEGER);
            CREATE TABLE IF NOT EXISTS deliveries (scope TEXT, event TEXT, result TEXT, PRIMARY KEY(scope,event));
        """)
        if disable:
            with db:
                db.execute(
                    "UPDATE subscriptions SET enabled=0,generation=generation+1 WHERE scope=? AND enabled=1",
                    (scope,),
                )
            return {"watch_ref": ref, "state": "disabled"}
        if settings is None:
            settings = {
                **dotenv_values(Path(__file__).resolve().parents[1] / ".env"),
                **os.environ,
            }
        webhook = _destination(settings.get("PS_FEISHU_WEBHOOK") or "")
        secret = settings.get("PS_FEISHU_SIGNING_SECRET") or ""
        with db:
            db.execute(
                "INSERT INTO subscriptions VALUES(?,1,1) ON CONFLICT(scope) DO UPDATE SET enabled=1, "
                "generation=generation+1 WHERE enabled=0",
                (scope,),
            )
            generation = db.execute(
                "SELECT generation FROM subscriptions WHERE scope=?", (scope,)
            ).fetchone()[0]

        # A fresh client keeps workbench authentication, proxy settings and headers off the webhook request.
        with httpx.Client(
            transport=transport, trust_env=False, timeout=8, follow_redirects=False
        ) as outbound:
            while True:
                current = db.execute(
                    "SELECT enabled,generation FROM subscriptions WHERE scope=?",
                    (scope,),
                ).fetchone()
                if current != (1, generation):
                    return {"watch_ref": ref, "state": "disabled"}
                try:
                    response = client.get("/api/runs/" + quote(run_id, safe=""))
                    if response.status_code in (401, 403, 404):
                        raise ValueError("The selected research run is unavailable")
                    response.raise_for_status()
                    run = response.json()
                except httpx.HTTPError:
                    if once:
                        raise ValueError("The workbench is unreachable") from None
                    time.sleep(poll_seconds)
                    continue
                if not isinstance(run, dict) or run.get("id") != run_id:
                    raise ValueError("The workbench returned an invalid run snapshot")
                status = run.get("status")
                outcome = "no matching event"
                if status in LABELS:
                    question = (
                        (run.get("pending") or {}).get("question_id", "")
                        if status == "waiting_input"
                        else ""
                    )
                    event = digest(
                        status + "\n" + str(question or run.get("updated_at", ""))
                    )
                    with db:
                        # Claim before posting, including across concurrent observers and process recovery.
                        inserted = db.execute(
                            "INSERT OR IGNORE INTO deliveries SELECT ?,?,'unconfirmed' "
                            "WHERE EXISTS(SELECT 1 FROM subscriptions WHERE scope=? AND enabled=1 AND generation=?)",
                            (scope, event, scope, generation),
                        ).rowcount
                    if inserted:
                        _post(
                            outbound,
                            webhook,
                            secret,
                            f"PaperScientist · {ref} · {LABELS[status]}",
                        )
                        with db:
                            db.execute(
                                "UPDATE deliveries SET result='sent' WHERE scope=? AND event=?",
                                (scope, event),
                            )
                        outcome = "sent"
                    else:
                        prior = db.execute(
                            "SELECT result FROM deliveries WHERE scope=? AND event=?",
                            (scope, event),
                        ).fetchone()
                        outcome = (
                            "disabled"
                            if prior is None
                            else (
                                "already sent" if prior[0] == "sent" else "unconfirmed"
                            )
                        )
                if once or status == "completed":
                    return {"watch_ref": ref, "state": status, "delivery": outcome}
                time.sleep(poll_seconds)
