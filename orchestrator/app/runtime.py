"""IntakeRunner — intake wired end-to-end (build-order Phase 3, contract §4).

Composes the Phase 2 spine into one runnable loop: conversation turns through the
gateway, deterministic marker detection, transcript persistence, the one-shot
extraction handoff through the validate-and-retry loop, and a stored IntakeRecord.
Gateway-agnostic: the same code runs on the fakes or the real OpenRouter adapter.
"""

from __future__ import annotations

from dataclasses import dataclass

from .enums import DataSensitivity
from .intake import (
    ConversationSession,
    TurnResult,
    build_extraction_envelope,
    run_conversation_turn,
)
from .invocation import AgentSpec
from .logging_audit import AuditLog
from .markers import MarkerMisuse
from .ports.datastore import Datastore
from .ports.gateway import ModelGateway
from .ports.identity import RequestorIdentity
from .retry_loop import run_structured
from .state_machine import Pipeline, Stage


@dataclass
class IntakeOutcome:
    status: str  # "record_ready" | "in_progress"
    pipeline: Pipeline
    transcript_reference: str | None = None
    record: dict | None = None


class IntakeRunner:
    """Drives one intake session from first turn to a stored structured record."""

    def __init__(
        self,
        *,
        gateway: ModelGateway,
        datastore: Datastore,
        audit: AuditLog,
        conversation_spec: AgentSpec,
        extraction_spec: AgentSpec,
        request_id: str,
        max_attempts: int = 3,
    ) -> None:
        self.gateway = gateway
        self.datastore = datastore
        self.audit = audit
        self.conversation_spec = conversation_spec
        self.extraction_spec = extraction_spec
        self.request_id = request_id
        self.max_attempts = max_attempts

    def open_session(self, session_id: str, identity: RequestorIdentity) -> ConversationSession:
        return ConversationSession(session_id=session_id, identity=identity)

    def submit_turn(self, session: ConversationSession, message: str) -> TurnResult:
        """One requestor turn. The caller advances only on result.marker.fired."""
        result = run_conversation_turn(self.gateway, self.conversation_spec, session, message)
        # Conversation sensitivity is unknown at this point -> treat as unspecified
        # (sensitive-until-confirmed), which redacts the payload in the audit log.
        self.audit.agent_call(
            request_id=self.request_id,
            stage=Stage.INTAKE_OPEN.value,
            agent_name=self.conversation_spec.name,
            prompt_version=self.conversation_spec.version,
            commit_hash=self.conversation_spec.commit_hash,
            input_rendered=session.render_conversation(),
            output=result.raw_agent_response,
            sensitivity=DataSensitivity.UNSPECIFIED,
            validation_result="n/a (prose)",
            retry_count=0,
        )
        if result.marker.is_misuse:
            classification = (
                result.marker.misuse.value if result.marker.misuse else MarkerMisuse.NOT_FINAL_LINE
            )
            self.audit.marker_misuse(
                request_id=self.request_id,
                classification=classification,
                agent_output=result.raw_agent_response,
            )
        return result

    def finalize(self, session: ConversationSession, pipeline: Pipeline, *, date: str) -> IntakeOutcome:
        """Marker fired: persist the transcript and run the extraction handoff (§4.4)."""
        pipeline.requestor_signoff()

        transcript = session.render_conversation()
        transcript_reference = f"txn/{date}/{self.request_id}"
        self.datastore.persist_transcript(transcript_reference, transcript)
        self.audit.marker_fired(
            request_id=self.request_id,
            transcript_reference=transcript_reference,
            agent_version=self.conversation_spec.version,
        )

        pipeline.extraction_complete()
        envelope = build_extraction_envelope(
            self.extraction_spec,
            auto_filled={
                "requestor": session.identity.requestor,
                "team": session.identity.team,
                "date": date,
                "transcript_reference": transcript_reference,
            },
            transcript=transcript,
        )
        record = run_structured(
            self.gateway,
            envelope,
            max_attempts=self.max_attempts,
            log_event=lambda e: self.audit.raw(self.request_id, e),
        )
        self.datastore.store_record(self.request_id, record)
        pipeline.data_sensitivity = DataSensitivity(record["data_sensitivity"])
        self.audit.agent_call(
            request_id=self.request_id,
            stage=Stage.INTAKE_EXTRACT.value,
            agent_name=self.extraction_spec.name,
            prompt_version=self.extraction_spec.version,
            commit_hash=self.extraction_spec.commit_hash,
            input_rendered=envelope.render(),
            output=record,
            sensitivity=pipeline.data_sensitivity,
            validation_result="valid",
            retry_count=0,
        )
        self.audit.sensitivity_overlay(
            request_id=self.request_id,
            original=pipeline.data_sensitivity,
            effective=_effective(pipeline.data_sensitivity),
            stage=Stage.INTAKE_EXTRACT.value,
        )
        return IntakeOutcome(
            status="record_ready",
            pipeline=pipeline,
            transcript_reference=transcript_reference,
            record=record,
        )


def _effective(value: DataSensitivity) -> DataSensitivity:
    from .sensitivity import effective_sensitivity

    return effective_sensitivity(value)
