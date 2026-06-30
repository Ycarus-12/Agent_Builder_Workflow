"""Outbound-email seam (Resend in production — context tool decisions).

All outbound email: gate-decision prompts to the Director, route-elsewhere
hand-offs, requestor sign-off and acceptance notices.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

from ..config import EmailerConfig, load_emailer_config


@dataclass(frozen=True)
class SentEmail:
    to: str
    subject: str
    body: str
    kind: str  # e.g. "gate_prompt", "route_elsewhere_handoff", "acceptance_notice"


class Emailer(ABC):
    @abstractmethod
    def send(self, *, to: str, subject: str, body: str, kind: str) -> None: ...


class InMemoryEmailer(Emailer):
    """Offline fake; collects sent mail for assertions."""

    def __init__(self) -> None:
        self.outbox: list[SentEmail] = []

    def send(self, *, to: str, subject: str, body: str, kind: str) -> None:
        self.outbox.append(SentEmail(to=to, subject=subject, body=body, kind=kind))


class EmailerError(RuntimeError):
    """Raised on a missing key/sender, transport failure, or a non-2xx Resend reply."""


class ResendEmailer(Emailer):
    """Production emailer over the Resend HTTP API (CLAUDE.md tool decisions).

    Keeps the seam: application code depends only on the Emailer port. The key and
    sender come from the environment, never code. `kind` rides along as a Resend
    tag so outbound mail stays auditable by category. `post` is injectable for
    tests; in production it lazily resolves to httpx, so the spine imports without
    httpx at rest (mirrors OpenRouterGateway).
    """

    def __init__(
        self,
        config: EmailerConfig | None = None,
        *,
        post: Callable[..., object] | None = None,
    ) -> None:
        self._config = config or load_emailer_config()
        self._post = post

    def send(self, *, to: str, subject: str, body: str, kind: str) -> None:
        if not self._config.has_key:
            raise EmailerError("RESEND_API_KEY is not set; cannot send mail")
        if not self._config.from_address:
            raise EmailerError("RESEND_FROM (sender address) is not set; cannot send mail")

        payload = {
            "from": self._config.from_address,
            "to": [to],
            "subject": subject,
            "text": body,
            "tags": [{"name": "kind", "value": kind}],
        }
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }

        post = self._post
        if post is None:
            import httpx  # lazy: the spine imports without httpx at rest

            post = httpx.post
        try:
            resp = post(f"{self._config.base_url}/emails", headers=headers, json=payload, timeout=30.0)
            resp.raise_for_status()
        except Exception as exc:  # transport boundary: surface as a seam error
            raise EmailerError(f"resend send failed ({kind}): {exc}") from exc
