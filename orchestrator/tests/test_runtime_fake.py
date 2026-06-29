"""Phase 3 loop proven on the fakes against the REAL prompts + REAL schema."""

import json

from jsonschema import Draft202012Validator

from app.agents import (
    intake_record_schema,
    load_intake_conversation_spec,
    load_intake_extraction_spec,
)
from app.logging_audit import AuditLog
from app.ports.datastore import InMemoryDatastore
from app.ports.gateway import FakeModelGateway
from app.ports.identity import RequestorIdentity
from app.runtime import IntakeRunner
from app.state_machine import Pipeline, Stage

# A sanitized, schema-valid IntakeRecord the fake extraction agent "emits".
VALID_RECORD = {
    "requestor": "J. Rivera", "team": "Professional Services", "date": "2026-06-29",
    "request_title": "Auto-create kickoff checklist on deal close",
    "problem_outcome": "Remove the manual kickoff checklist after each deal close.",
    "current_workaround": "Built by hand in the work tool.",
    "success_criteria": "Checklist auto-created and owner notified on deal close.",
    "frequency": "a few times a week", "who_is_affected": "requestor",
    "time_cost": "~20 min", "deadline": None,
    "systems_involved": ["CRM", "work-management tool"],
    "data_sensitivity": "internal", "customer_facing": False,
    "solution_idea": None, "attachments": [],
    "context_constraints_nuance": None,
    "acceptance_criteria": ["auto-create checklist", "notify owner"],
    "transcript_reference": "txn/2026-06-29/req-1",
}


def _runner():
    store = InMemoryDatastore()
    gateway = FakeModelGateway(
        {
            "intake-conversation": [
                "Tell me more about the problem.",
                "Recorded your sign-off.\n\n[[INTAKE_SIGNOFF_CONFIRMED]]",
            ],
            "intake-extraction": [json.dumps(VALID_RECORD)],
        }
    )
    runner = IntakeRunner(
        gateway=gateway,
        datastore=store,
        audit=AuditLog(store),
        conversation_spec=load_intake_conversation_spec(),
        extraction_spec=load_intake_extraction_spec(),
        request_id="req-1",
    )
    return runner, store


def test_full_intake_loop_produces_valid_record():
    runner, store = _runner()
    identity = RequestorIdentity("J. Rivera", "Professional Services")
    session = runner.open_session("s1", identity)
    pipeline = Pipeline()

    t1 = runner.submit_turn(session, "I need a Zapier zap.")
    assert not t1.marker.fired
    t2 = runner.submit_turn(session, "Yes, that's correct.")
    assert t2.marker.fired

    outcome = runner.finalize(session, pipeline, date="2026-06-29")

    # Record is schema-valid against the locked IntakeRecord contract.
    Draft202012Validator(intake_record_schema()).validate(outcome.record)
    assert outcome.status == "record_ready"
    assert outcome.transcript_reference == "txn/2026-06-29/req-1"

    # Persisted: transcript + record; pipeline advanced into analysis.
    assert store.get_record("req-1")["request_title"].startswith("Auto-create")
    assert store.get_transcript("txn/2026-06-29/req-1") is not None
    assert pipeline.stage is Stage.ANALYSIS

    # Audit captured the agent calls and the marker; sensitivity overlay logged.
    events = {e["event"] for e in store.events}
    assert {"agent_call", "marker_fired", "sensitivity_overlay"} <= events


def test_auto_fill_reaches_extraction_envelope():
    runner, store = _runner()
    identity = RequestorIdentity("J. Rivera", "Professional Services")
    session = runner.open_session("s1", identity)
    runner.submit_turn(session, "hello")
    runner.submit_turn(session, "yes")
    runner.finalize(session, Pipeline(), date="2026-06-29")
    # The extraction call envelope carried the orchestrator-supplied [Auto-filled].
    extraction_call = [c for c in runner.gateway.calls if c[0] == "intake-extraction"][0]
    assert "[Auto-filled]" in extraction_call[1]
    assert "J. Rivera" in extraction_call[1]
    assert "txn/2026-06-29/req-1" in extraction_call[1]
