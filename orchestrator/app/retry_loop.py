"""The validate-and-retry loop for structured outputs (orchestrator-contract §5).

Every structured-output agent uses this loop: invoke, validate against the
declared JSON Schema, and on failure re-invoke with a [Validation feedback]
block naming the specific violations. On exhausted retries it escalates to the
Director — it NEVER silently proceeds and NEVER silently falls back to a larger
model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from jsonschema import Draft202012Validator

from .invocation import InputEnvelope, OutputMode
from .ports.gateway import ModelGateway

DEFAULT_MAX_ATTEMPTS = 3  # initial + 2 retries; tunable per agent


@dataclass
class Attempt:
    number: int
    raw_output: str
    errors: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass
class RetryExhausted(Exception):
    """Raised when MAX_ATTEMPTS is hit without a valid output (escalation)."""

    agent_name: str
    attempts: list[Attempt]

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"structured_output_failed: {self.agent_name} after "
            f"{len(self.attempts)} attempt(s)"
        )


def _schema_errors(validator: Draft202012Validator, raw_output: str) -> tuple[dict | None, list[str]]:
    """Parse + validate one raw output. Returns (parsed_or_none, errors)."""
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        return None, [f"(root): output is not valid JSON: {exc.msg}"]
    errors = []
    for err in sorted(validator.iter_errors(parsed), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "(root)"
        errors.append(f"{loc}: {err.message}")
    return (parsed if not errors else None), errors


def _feedback(errors: list[str]) -> str:
    lines = "\n".join(f"- {e}" for e in errors)
    return (
        "Your previous output did not satisfy the required schema. Fix exactly "
        "these violations and re-emit the full object:\n" + lines
    )


def run_structured(
    gateway: ModelGateway,
    envelope: InputEnvelope,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    log_event: Callable[[dict], None] | None = None,
) -> dict:
    """Drive the validate-and-retry loop; return the validated object.

    Raises RetryExhausted (the escalation signal) when no attempt validates.
    """
    spec = envelope.spec
    if spec.output_mode is not OutputMode.STRUCTURED:
        raise ValueError(f"{spec.name}: run_structured requires a STRUCTURED agent")
    validator = Draft202012Validator(spec.output_schema)

    attempts: list[Attempt] = []
    current = envelope
    for n in range(1, max_attempts + 1):
        raw = gateway.complete(current)
        parsed, errors = _schema_errors(validator, raw)
        attempt = Attempt(number=n, raw_output=raw, errors=errors)
        attempts.append(attempt)

        if attempt.valid:
            return parsed  # type: ignore[return-value]

        if log_event is not None:
            log_event(
                {
                    "event": "validation_failure",
                    "agent": spec.name,
                    "attempt": n,
                    "schema_errors": errors,
                }
            )
        if n >= max_attempts:
            if log_event is not None:
                log_event(
                    {
                        "event": "retry_exhausted",
                        "agent": spec.name,
                        "attempts": [a.errors for a in attempts],
                    }
                )
            raise RetryExhausted(agent_name=spec.name, attempts=attempts)

        current = envelope.with_feedback(_feedback(errors))

    raise AssertionError("unreachable")  # pragma: no cover
