"""ResendEmailer: payload mapping, the no-secret guards, and transport errors.

No network — a fake `post` captures the request the adapter would send.
"""

import pytest

from app.config import EmailerConfig
from app.ports.emailer import EmailerError, ResendEmailer


class _Resp:
    def __init__(self, status: int = 200) -> None:
        self.status = status

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")


def _cfg(**over) -> EmailerConfig:
    base = dict(base_url="https://api.resend.com", api_key="re_test", from_address="bot@acme.test")
    base.update(over)
    return EmailerConfig(**base)


def test_send_maps_to_resend_payload():
    captured = {}

    def fake_post(url, *, headers, json, timeout):
        captured.update(url=url, headers=headers, json=json, timeout=timeout)
        return _Resp(200)

    ResendEmailer(_cfg(), post=fake_post).send(
        to="director@acme.test", subject="Decision needed: gate_1a", body="costed list", kind="gate_prompt"
    )

    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"]["Authorization"] == "Bearer re_test"
    body = captured["json"]
    assert body["from"] == "bot@acme.test"
    assert body["to"] == ["director@acme.test"]
    assert body["subject"] == "Decision needed: gate_1a"
    assert body["text"] == "costed list"
    assert body["tags"] == [{"name": "kind", "value": "gate_prompt"}]


def test_missing_key_raises_before_any_send():
    sent = []
    emailer = ResendEmailer(_cfg(api_key=None), post=lambda *a, **k: sent.append(1))
    with pytest.raises(EmailerError, match="RESEND_API_KEY"):
        emailer.send(to="x@y.z", subject="s", body="b", kind="gate_prompt")
    assert not sent  # guard fires before the transport is touched


def test_missing_sender_raises():
    emailer = ResendEmailer(_cfg(from_address=None), post=lambda *a, **k: _Resp(200))
    with pytest.raises(EmailerError, match="RESEND_FROM"):
        emailer.send(to="x@y.z", subject="s", body="b", kind="gate_prompt")


def test_non_2xx_surfaces_as_emailer_error():
    emailer = ResendEmailer(_cfg(), post=lambda *a, **k: _Resp(422))
    with pytest.raises(EmailerError, match="resend send failed"):
        emailer.send(to="x@y.z", subject="s", body="b", kind="acceptance_notice")
