"""Durable resume: a request is driven, the runner discarded, then rebuilt from the
datastore snapshot — proving each gate decision can arrive in a fresh process."""

import json
from pathlib import Path

import yaml

from app.composition import build_services, make_pipeline_runner, rehydrate_runner
from app.enums import DataSensitivity
from app.pipeline_runner import RunState
from app.ports.chat import ChatTurn, ToolCall
from app.request_store import RequestStore
from app.state_machine import Gate1aDecision, Pipeline, Stage

_FIX = Path(__file__).resolve().parents[1] / "evals" / "fixtures"


def _ro(rel: str) -> str:
    out = yaml.safe_load((_FIX / rel).read_text(encoding="utf-8"))["recorded_output"]
    return out if isinstance(out, str) else json.dumps(out)


def _ro_dict(rel: str) -> dict:
    return json.loads(_ro(rel))


def _triage_build_light() -> str:
    t = _ro_dict("triage/T6_build.yaml")
    t["options"][0]["weight"] = "light"
    return json.dumps(t)


def _services_at_analysis(sec_vuln="security_vuln/SV2_clean.yaml"):
    svc = build_services("offline")
    gw = svc.gateway
    gw.script_chat("stack-check", [ChatTurn(tool_calls=[ToolCall("c1", "emit_finding", _ro_dict("stack_check/S3_empty.yaml"))])])
    gw.script("triage-recommender", [_triage_build_light()])
    gw.script("cost-estimation-rom", [_ro("rom/R2_build_ai.yaml")])
    gw.script("cost-estimation-deepdive", [_ro("deepdive/D3_build_vs_buy_n2.yaml")])
    gw.script("build-agent", [_ro("build/B1_code_complete.yaml")])
    gw.script("functional-qa", [_ro("functional_qa/Q1_code_pass.yaml")])
    gw.script("security-vulnerabilities", [_ro(sec_vuln)])
    gw.script("security-governance", [_ro("security_gov/SG1_findings.yaml")])
    p = Pipeline()
    p.requestor_signoff()
    p.extraction_complete()
    p.data_sensitivity = DataSensitivity.INTERNAL
    state = RunState(
        intake_record={"request_title": "Checklist", "problem": "p", "data_sensitivity": "internal", "acceptance_criteria": []},
        transcript="Requestor: hi",
    )
    return svc, p, state


def test_pipeline_serialization_round_trips():
    svc, p, _ = _services_at_analysis()
    p.weight  # default
    restored = Pipeline.from_dict(p.to_dict())
    assert restored.to_dict() == p.to_dict()
    assert restored.stage is p.stage and restored.analysis_step is p.analysis_step


def test_each_decision_in_a_fresh_rehydrated_runner():
    svc, p, state = _services_at_analysis()
    make_pipeline_runner(svc, pipeline=p, state=state, request_id="req-1").advance()  # -> gate_1a, then discarded

    # fresh process #1: current_step is read-only (no agent calls), reports gate_1a
    before = len(svc.gateway.calls)
    r = rehydrate_runner(svc, "req-1")
    assert r.current_step().stage == Stage.GATE_1A.value
    assert len(svc.gateway.calls) == before
    assert r.resume_gate_1a(Gate1aDecision.DEEP_DIVE, selected_options=("opt_001",)).stage == Stage.GATE_1B.value

    # fresh process #2
    r = rehydrate_runner(svc, "req-1")
    assert r.current_step().stage == Stage.GATE_1B.value
    assert r.resume_gate_1b(approved=True).stage == Stage.GATE_2.value

    # fresh process #3
    r = rehydrate_runner(svc, "req-1")
    assert r.current_step().stage == Stage.GATE_2.value
    step = r.resume_gate_2(accepted=True)
    assert step.kind == "terminal" and step.stage == Stage.DEPLOY_AND_REGISTER.value


def test_security_outcome_recomputed_on_rehydrate():
    # SV1 carries a High finding -> the rehydrated runner must re-derive "to Director".
    svc, p, state = _services_at_analysis(sec_vuln="security_vuln/SV1_findings.yaml")
    r = make_pipeline_runner(svc, pipeline=p, state=state, request_id="req-2")
    r.advance()
    r.resume_gate_1a(Gate1aDecision.DEEP_DIVE, selected_options=("opt_001",))
    r.resume_gate_1b(approved=True)  # runs build/qa/security -> awaiting adjudication

    fresh = rehydrate_runner(svc, "req-2")
    assert fresh.current_step().kind == "awaiting_security_adjudication"
    assert fresh.resume_security_adjudication(cleared=True).stage == Stage.GATE_2.value


def test_request_store_lists_in_flight():
    svc, p, state = _services_at_analysis()
    make_pipeline_runner(svc, pipeline=p, state=state, request_id="req-1").advance()
    summaries = RequestStore(svc.datastore).summaries()
    assert [s.request_id for s in summaries] == ["req-1"]
    assert summaries[0].status == "awaiting_gate"
    assert summaries[0].request_title == "Checklist"
