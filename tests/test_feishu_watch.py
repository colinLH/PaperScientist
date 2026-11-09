import hashlib
import hmac
import base64
import json

import httpx
import pytest

from paperscientist.feishu_watch import watch


def test_explicit_watch_minimal_signed_and_not_repeated(tmp_path):
    sent = []
    config = {
        "PS_FEISHU_WEBHOOK": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
        "PS_FEISHU_SIGNING_SECRET": "fixture-signature",
    }
    db = tmp_path / "watch.db"
    run = {
        "id": "run-1",
        "status": "waiting_input",
        "pending": {"question_id": "q1", "question": "private-idea"},
        "objective": "private-idea",
    }

    def outbound(req):
        data = json.loads(req.content)
        assert "private-idea" not in str(data) and run["id"] not in str(data)
        sig = hmac.new(
            (data["timestamp"] + "\n" + config["PS_FEISHU_SIGNING_SECRET"]).encode(),
            b"",
            hashlib.sha256,
        ).digest()
        assert base64.b64encode(sig).decode() == data["sign"]
        sent.append(data)
        return httpx.Response(200, json={"code": 0})

    with httpx.Client(
        base_url="http://testserver",
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=run)),
    ) as c:

        def observe():
            return watch(
                c,
                "run-1",
                once=True,
                state_path=db,
                settings=config,
                transport=httpx.MockTransport(outbound),
            )

        assert (
            observe()["delivery"] == "sent" and observe()["delivery"] == "already sent"
        )
        run["pending"]["question_id"] = "q2"
        assert observe()["delivery"] == "sent"
        assert watch(c, "run-1", disable=True, state_path=db)["state"] == "disabled"
        assert len(sent) == 2
    assert b"fixture-signature" not in db.read_bytes()


def test_uncertain_delivery_doesnt_retry_or_disclose_webhook(tmp_path):
    def fail(req):
        raise httpx.ConnectError(str(req.url))

    with httpx.Client(
        base_url="http://localhost",
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, json={"id": "test", "status": "completed"})
        ),
    ) as c:
        args = dict(
            once=True,
            state_path=tmp_path / "state.db",
            settings={
                "PS_FEISHU_WEBHOOK": "https://open.feishu.cn/open-apis/bot/v2/hook/private-test-value"
            },
            transport=httpx.MockTransport(fail),
        )
        with pytest.raises(ValueError, match="unconfirmed") as err:
            watch(c, "test", **args)
        assert "private-test-value" not in str(err.value)
        assert watch(c, "test", **args)["delivery"] == "unconfirmed"
