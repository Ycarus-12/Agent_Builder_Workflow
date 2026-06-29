"""Identity seam (SSO / identity provider — orchestrator-contract §4.1).

`requestor`, `team`, `date`, and `transcript_reference` are NEVER authored by the
model. The orchestrator resolves identity from the authenticated session here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class RequestorIdentity:
    requestor: str  # authenticated session identity
    team: str       # team/department attribute on the directory record


class IdentityProvider(ABC):
    @abstractmethod
    def resolve(self, session_id: str) -> RequestorIdentity: ...


class FakeIdentityProvider(IdentityProvider):
    """Offline fake; maps session ids to pre-seeded identities."""

    def __init__(self, identities: dict[str, RequestorIdentity] | None = None) -> None:
        self._identities = dict(identities or {})

    def register(self, session_id: str, identity: RequestorIdentity) -> None:
        self._identities[session_id] = identity

    def resolve(self, session_id: str) -> RequestorIdentity:
        if session_id not in self._identities:
            raise KeyError(f"no identity registered for session '{session_id}'")
        return self._identities[session_id]
