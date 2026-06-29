"""Fake end-to-end flow: a request driven intake -> deploy through the spine.

No live model and no real SaaS — everything runs on the in-memory fakes. This
proves the modules compose: conversation loop + marker detection + extraction
retry loop + state machine + audit log + seams.
"""

import json

from app.enums import DataSensitivity, Outcome, Weight
from app.intake import (
    ConversationSession,
    build_extraction_envelope,
    run_conversation_turn,
)
from app.invocation import AgentSpec, OutputMode, Tier
from app.logging_audit import AuditLog
from app.ports import (
    FakeIdentityProvider,
    FakeModelGateway,
    InMemoryDatastore,
    InMemoryEmailer,
    RequestorIdentity,
)
from app.retry_loop import run_structured
from app.state_machine import AnalysisStep, Gate1aDecision, Pipeline, Stage

CONV_SPEC = AgentSpec(
    name="intake-conversation", version="1.0.0", commit_hash="c0ffee",
    tier=Tier.MID, output_mode=OutputMode.PROSE,
    block_names=("requestor_identity", "conversation"),
)

EXTRACT_SCHEMA = {
    "type": "object",
    "required": ["problem", "data_sensitivity", "acceptance_criteria"],
    "properties": {
        "problem": {"type": "string"},
        "data_sensitivity": {
            "enum": ["none", "internal", "customer", "financial", "regulated", "unspecified"]
        },
        "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": False,
}

EXTRACT_SPEC = AgentSpec(
    name="intake-extraction", version="1.0.0", commit_hash="c0ffee",
    tier=Tier.SLM, output_mode=OutputMode.STRUCTURED,
    block_names=("Auto-filled", "TRANSCRIPT"), output_schema=EXTRACT_SCHEMA,
)

EXTRACT_JSON = json.dumps(
    {
        "problem": "deal close -> manual kickoff checklist",
        "data_sensitivity": "internal",
        "acceptance_criteria": ["auto-create checklist", "notify owner", "log run"],
    }
)


def test_request_flows_intake_to_deploy():
    # -- seams (all fakes) ------------------------------------------------
    idp = FakeIdentityProvider({"s1": RequestorIdentity("J. Rivera", "Professional Services")})
    gateway = FakeModelGateway(
        {
            "intake-conversation": [
                "Thanks! What problem are you trying to solve?",
                "Got it — auto-create the checklist when a deal closes.\n\n"
                "[[INTAKE_SIGNOFF_CONFIRMED]]",
            ],
            "intake-extraction": [EXTRACT_JSON],
        }
    )
    store = InMemoryDatastore()
    emailer = InMemoryEmailer()
    audit = AuditLog(store)
    request_id = "req-1"

    # -- intake conversation loop (§4.2) ---------------------------------
    identity = idp.resolve("s1")
    session = ConversationSession("s1", identity)
    t1 = run_conversation_turn(gateway, CONV_SPEC, session, "I need a Zapier zap.")
    assert not t1.marker.fired
    t2 = run_conversation_turn(gateway, CONV_SPEC, session, "Yes, that's correct.")
    assert t2.marker.fired
    assert "[[INTAKE_SIGNOFF_CONFIRMED]]" not in t2.visible_reply  # stripped (§4.3)

    pipeline = Pipeline(weight=Weight.LIGHT)
    pipeline.requestor_signoff()  # close of intake_open (stop point: requestor confirms)

    # persist transcript + audit the marker
    transcript_reference = "txn/2026-06-29/rivera-01"
    store.persist_transcript(transcript_reference, session.render_conversation())
    audit.marker_fired(
        request_id=request_id, transcript_reference=transcript_reference, agent_version="1.0.0"
    )

    # -- extraction handoff (§4.4) via the retry loop --------------------
    pipeline.extraction_complete()
    env = build_extraction_envelope(
        EXTRACT_SPEC,
        auto_filled={
            "requestor": identity.requestor,
            "team": identity.team,
            "date": "2026-06-29",
            "transcript_reference": transcript_reference,
        },
        transcript=store.get_transcript(transcript_reference),
    )
    record = run_structured(gateway, env, log_event=lambda e: audit.raw(request_id, e))
    store.store_record(request_id, record)
    pipeline.data_sensitivity = DataSensitivity(record["data_sensitivity"])
    audit.agent_call(
        request_id=request_id, stage="intake_extract", agent_name=EXTRACT_SPEC.name,
        prompt_version=EXTRACT_SPEC.version, commit_hash=EXTRACT_SPEC.commit_hash,
        input_rendered=env.render(), output=record,
        sensitivity=pipeline.data_sensitivity, validation_result="valid", retry_count=0,
    )

    # -- analysis sub-pipeline -------------------------------------------
    pipeline.advance_analysis()  # -> triage
    assert pipeline.analysis_step is AnalysisStep.TRIAGE
    pipeline.set_triage_recommendation(Outcome.BUILD)
    pipeline.advance_analysis()  # -> cost_rom
    pipeline.advance_analysis()  # -> gate_1a
    assert pipeline.is_stop_point

    # -- gate 1a: Director picks an option for deep-dive -----------------
    emailer.send(to="director@example.com", subject="Gate 1a", body="costed list", kind="gate_prompt")
    audit.gate_decision(
        request_id=request_id, stage="gate_1a", decision="deep_dive",
        decided_by="Director", rationale="option 1 looks strong",
    )
    pipeline.apply_gate_1a(Gate1aDecision.DEEP_DIVE, selected_options=("opt-1",))

    # -- deep-dive, spend gate, build, QA, security, accept --------------
    pipeline.deepdive_complete()
    pipeline.apply_gate_1b(approved=True)
    pipeline.build_complete()
    pipeline.apply_qa(passed=True)
    pipeline.apply_security(passed=True)  # light + internal -> no R&D sign-off
    pipeline.apply_gate_2(accepted=True)

    # -- assertions -------------------------------------------------------
    assert pipeline.stage is Stage.DEPLOY_AND_REGISTER
    assert pipeline.is_terminal
    assert store.get_record(request_id)["problem"].startswith("deal close")
    assert store.get_transcript(transcript_reference) is not None
    event_types = {e["event"] for e in store.events}
    assert {"marker_fired", "agent_call", "gate_decision"} <= event_types
    assert any(m.kind == "gate_prompt" for m in emailer.outbox)
