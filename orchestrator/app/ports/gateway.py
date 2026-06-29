"""Model-access seam (orchestrator-contract §1, context §6).

All model calls route through this provider-neutral port. Production swaps the
gateway (OpenRouter/BYOK in dev/test -> a compliant gateway in prod) WITHOUT
contract changes. The orchestrator never hardwires a provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict

from ..invocation import InputEnvelope


class ModelGateway(ABC):
    """Provider-neutral inference port."""

    @abstractmethod
    def complete(self, envelope: InputEnvelope) -> str:
        """Run one inference and return the agent's raw text output.

        For STRUCTURED agents the returned string is the JSON payload produced
        by constrained decoding; validation happens in the retry loop, not here.
        """


class FakeModelGateway(ModelGateway):
    """Deterministic gateway for tests and the spine's offline end-to-end flow.

    Responses are scripted per agent name as an ordered list consumed one call at
    a time, so a retry loop can be driven through fail-then-succeed sequences.
    """

    def __init__(self, scripts: dict[str, list[str]] | None = None) -> None:
        self._scripts: dict[str, list[str]] = {k: list(v) for k, v in (scripts or {}).items()}
        self._cursor: dict[str, int] = defaultdict(int)
        self.calls: list[tuple[str, str]] = []  # (agent_name, rendered_envelope)

    def script(self, agent_name: str, responses: list[str]) -> None:
        self._scripts[agent_name] = list(responses)
        self._cursor[agent_name] = 0

    def complete(self, envelope: InputEnvelope) -> str:
        name = envelope.spec.name
        self.calls.append((name, envelope.render()))
        responses = self._scripts.get(name)
        if not responses:
            raise KeyError(f"FakeModelGateway has no script for agent '{name}'")
        idx = self._cursor[name]
        if idx >= len(responses):
            raise IndexError(
                f"FakeModelGateway exhausted script for '{name}' "
                f"({len(responses)} responses, asked for #{idx + 1})"
            )
        self._cursor[name] += 1
        return responses[idx]
