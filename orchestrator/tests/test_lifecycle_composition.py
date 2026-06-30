"""Full request lifecycle through the composition root: intake -> deploy, offline.

One FakeModelGateway serves every agent (complete() for structured/prose, chat()
for stack-check). Every scripted reply is a schema-valid recorded_output harvested
from the eval fixtures. This is the capstone: the wired services + both runners +
the intake->pipeline handoff compose into a single runnable flow.
"""

import json
from pathlib import Path

import yaml

from app.composition import (
    build_services,
    make_intake_runner,
    pipeline_runner_after_intake,
)
from app.ports import RequestorIdentity
from app.ports.chat import ChatTurn, ToolCall
from app.ports.gateway import FakeModelGateway
from app.state_machine import Gate1aDecision, Pipeline, Stage

_FIX = Path(__file__).resolve().parents[1] / "evals" / "fixtures"


def _ro(rel: str) -> str:
    out = yaml.safe_load((_FIX / rel).read_text(encoding="utf-8"))["recorded_output"]
    return out if isinstance(out, str) else json.dumps(out)


def _ro_dict(rel: str) -> dict:
    return json.loads(_ro(rel))


def _extract_internal() -> str:
    """A valid intake_record (E1) with sensitivity relaxed to internal (no R&D path)."""
    rec = _ro_dict("extraction/E1_rich.yaml")
    rec["data_sensitivity"] = "internal"
    return json.dumps(rec)


def _triage_build_light() -> str:
    t = _ro_dict("triage/T6_build.yaml")
    t["options"][0]["weight"] = "light"
    return json.dumps(t)


def _script(gw: FakeModelGateway) -> None:
    gw.script("intake-conversation", [
        "What problem are you solving?",
        "Got it — auto-create the checklist on deal close.\n\n[[INTAKE_SIGNOFF_CONFIRMED]]",
    ])
    gw.script("intake-extraction", [_extract_internal()])
    gw.script_chat("stack-check", [
        ChatTurn(tool_calls=[ToolCall("c1", "emit_finding", _ro_dict("stack_check/S3_empty.yaml"))])
    ])
    gw.script("triage-recommender", [_triage_build_light()])
    gw.script("cost-estimation-rom", [_ro("rom/R2_build_ai.yaml")])
    gw.script("cost-estimation-deepdive", [_ro("deepdive/D3_build_vs_buy_n2.yaml")])
    gw.script("build-agent", [_ro("build/B1_code_complete.yaml")])
    gw.script("functional-qa", [_ro("functional_qa/Q1_code_pass.yaml")])
    gw.script("security-vulnerabilities", [_ro("security_vuln/SV2_clean.yaml")])
    gw.script("security-governance", [_ro("security_gov/SG1_findings.yaml")])


def test_intake_through_deploy_via_composition():
    svc = build_services("offline")
    _script(svc.gateway)
    svc.identity.register("s1", RequestorIdentity("J. Rivera", "Professional Services"))

    # -- intake: conversation -> marker -> extraction -> stored record --------
    intake = make_intake_runner(svc, request_id="req-1")
    session = intake.open_session("s1", svc.identity.resolve("s1"))
    intake.submit_turn(session, "I need a checklist zap.")
    t2 = intake.submit_turn(session, "Yes, that's correct.")
    assert t2.marker.fired
    outcome = intake.finalize(session, Pipeline(), date="2026-06-30")
    assert outcome.status == "record_ready"

    # -- handoff to the pipeline driver --------------------------------------
    runner = pipeline_runner_after_intake(svc, outcome, request_id="req-1")
    assert runner.state.intake_record["data_sensitivity"] == "internal"

    step = runner.advance()
    assert step.stage == Stage.GATE_1A.value
    step = runner.resume_gate_1a(Gate1aDecision.DEEP_DIVE, selected_options=("opt_001",))
    assert step.stage == Stage.GATE_1B.value
    step = runner.resume_gate_1b(approved=True)
    assert step.stage == Stage.GATE_2.value
    step = runner.resume_gate_2(accepted=True)
    assert step.kind == "terminal" and step.stage == Stage.DEPLOY_AND_REGISTER.value

    # one datastore carried the whole lifecycle: transcript, record, state, audit.
    assert svc.datastore.get_transcript(outcome.transcript_reference) is not None
    assert svc.datastore.get_record("req-1:state")["build_manifest"] is not None
    agents = {e["agent"] for e in svc.datastore.events if e["event"] == "agent_call"}
    assert {"intake-conversation", "intake-extraction", "stack-check", "triage-recommender",
            "build-agent", "functional-qa", "security-vulnerabilities", "security-governance"} <= agents
