"""Logging & audit (orchestrator-contract §8).

The audit trail lives in the application database (the Datastore port), never the
AI gateway. Payloads tagged customer/financial/regulated/unspecified are redacted
by default; only metadata is retained at-rest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .enums import DataSensitivity
from .ports.datastore import Datastore
from .sensitivity import is_sensitive

_REDACTED = "[REDACTED:sensitivity]"


@dataclass
class AuditLog:
    """Append-only event recorder backed by the operational datastore."""

    datastore: Datastore
    # A monotonic counter stands in for a real clock so the spine stays
    # deterministic and offline; production stamps wall-clock ISO-8601 timestamps.
    _seq: int = field(default=0, init=False)

    def _emit(self, request_id: str | None, event: dict[str, Any]) -> dict[str, Any]:
        self._seq += 1
        record = {"seq": self._seq, "request_id": request_id, **event}
        self.datastore.append_event(record)
        return record

    def _payload(self, value: Any, sensitivity: DataSensitivity) -> Any:
        return _REDACTED if is_sensitive(sensitivity) else value

    # -- the §8 event table ----------------------------------------------
    def agent_call(
        self,
        *,
        request_id: str,
        stage: str,
        agent_name: str,
        prompt_version: str,
        commit_hash: str,
        input_rendered: str,
        output: Any,
        sensitivity: DataSensitivity,
        validation_result: str,
        retry_count: int,
        latency_ms: float | None = None,
    ) -> dict[str, Any]:
        return self._emit(
            request_id,
            {
                "event": "agent_call",
                "stage": stage,
                "agent": agent_name,
                "prompt_version": prompt_version,
                "commit_hash": commit_hash,
                "input": self._payload(input_rendered, sensitivity),
                "output": self._payload(output, sensitivity),
                "validation_result": validation_result,
                "retry_count": retry_count,
                "latency_ms": latency_ms,
            },
        )

    def marker_fired(self, *, request_id: str, transcript_reference: str, agent_version: str):
        return self._emit(
            request_id,
            {
                "event": "marker_fired",
                "transcript_reference": transcript_reference,
                "agent_version": agent_version,
            },
        )

    def marker_misuse(self, *, request_id: str, classification: str, agent_output: str):
        return self._emit(
            request_id,
            {"event": "marker_misuse", "classification": classification, "output": agent_output},
        )

    def gate_decision(
        self, *, request_id: str, stage: str, decision: str, decided_by: str, rationale: str
    ):
        return self._emit(
            request_id,
            {
                "event": "gate_decision",
                "stage": stage,
                "decision": decision,
                "decided_by": decided_by,
                "rationale": rationale,
            },
        )

    def sensitivity_overlay(
        self, *, request_id: str, original: DataSensitivity, effective: DataSensitivity, stage: str
    ):
        return self._emit(
            request_id,
            {
                "event": "sensitivity_overlay",
                "original": original.value,
                "effective": effective.value,
                "stage": stage,
            },
        )

    def session_abandoned(self, *, request_id: str, last_active_seq: int, timeout: str):
        return self._emit(
            request_id,
            {"event": "session_abandoned", "last_active_seq": last_active_seq, "timeout": timeout},
        )

    def raw(self, request_id: str | None, event: dict[str, Any]) -> dict[str, Any]:
        """Escape hatch for events surfaced by sub-components (e.g. retry loop)."""
        return self._emit(request_id, event)
