"""Outbound-email seam (Resend in production — context tool decisions).

All outbound email: gate-decision prompts to the Director, route-elsewhere
hand-offs, requestor sign-off and acceptance notices.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


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
