"""PipelineRunner: a request driven past intake through the whole spine.

Every scripted agent reply is a real `recorded_output` harvested from the eval
fixtures, so each one is schema-valid and the runner exercises the live
validate-and-retry path — not a stubbed shortcut. Runs entirely on the fakes.
"""

import json
from pathlib import Path

import yaml

from app.enums import DataSensitivity
from app.logging_audit import AuditLog
from app.pipeline_runner import PipelineRunner, RunState
from app.ports.chat import ChatTurn, FakeChatGateway, ToolCall
from app.ports.gateway import FakeModelGateway
from app.ports.datastore import InMemoryDatastore
from app.ports.emailer import InMemoryEmailer
from app.state_machine import Gate1aDecision, Pipeline, Stage

_FIX = Path(__file__).resolve().parents[1] / "evals" / "fixtures"


def _ro(rel: str) -> str:
    """Return a fixture's recorded_output as a JSON string."""
    data = yaml.safe_load((_FIX / rel).read_text(encoding="utf-8"))
    out = data["recorded_output"]
    return out if isinstance(out, str) else json.dumps(out)


def _ro_dict(rel: str) -> dict:
    return json.loads(_ro(rel))


def _triage_build_light() -> str:
    """T6 (build, opt_001) with the option weight relaxed to light for a no-R&D run."""
    t = _ro_dict("triage/T6_build.yaml")
    t["options"][0]["weight"] = "light"
    return json.dumps(t)


def _intake_record() -> dict:
    return {
        "request_title": "Auto-create deal checklist",
        "problem": "deal close -> manual kickoff checklist",
        "data_sensitivity": "internal",
        "acceptance_criteria": ["auto-create checklist", "notify owner", "log run"],
    }


def _runner(gateway: FakeModelGateway, **overrides) -> PipelineRunner:
    store = InMemoryDatastore()
    pipeline = Pipeline()
    pipeline.requestor_signoff()
    pipeline.extraction_complete()  # -> analysis:stack_check
    pipeline.data_sensitivity = DataSensitivity.INTERNAL
    chat = FakeChatGateway(
        {"stack-check": [ChatTurn(tool_calls=[ToolCall("c1", "emit_finding", _ro_dict("stack_check/S3_empty.yaml"))])]}
    )
    kwargs = dict(
        pipeline=pipeline,
        state=RunState(intake_record=_intake_record(), transcript="Requestor: I need a checklist zap."),
        request_id="req-1",
        gateway=gateway,
        chat_gateway=chat,
        datastore=store,
        emailer=InMemoryEmailer(),
        audit=AuditLog(store),
        registry_source=None,  # stack-check fixture does not search, so it is unused
    )
    kwargs.update(overrides)
    return PipelineRunner(**kwargs)


def _analysis_script() -> dict:
    return {
        "triage-recommender": [_triage_build_light()],
        "cost-estimation-rom": [_ro("rom/R2_build_ai.yaml")],
        "cost-estimation-deepdive": [_ro("deepdive/D3_build_vs_buy_n2.yaml")],
    }


# == the full happy path =====================================================
def test_request_flows_intake_to_deploy():
    gateway = FakeModelGateway({
        **_analysis_script(),
        "build-agent": [_ro("build/B1_code_complete.yaml")],
        "functional-qa": [_ro("functional_qa/Q1_code_pass.yaml")],
        "security-vulnerabilities": [_ro("security_vuln/SV2_clean.yaml")],
        "security-governance": [_ro("security_gov/SG1_findings.yaml")],
    })
    r = _runner(gateway)

    step = r.advance()
    assert step.kind == "awaiting_gate" and step.stage == Stage.GATE_1A.value
    assert step.payload["recommendation"]["outcome"] == "build"

    step = r.resume_gate_1a(Gate1aDecision.DEEP_DIVE, selected_options=("opt_001",))
    assert step.kind == "awaiting_gate" and step.stage == Stage.GATE_1B.value

    step = r.resume_gate_1b(approved=True)
    assert step.kind == "awaiting_gate" and step.stage == Stage.GATE_2.value
    assert step.payload["build_manifest"]["build_status"] == "complete"

    step = r.resume_gate_2(accepted=True)
    assert step.kind == "terminal" and step.stage == Stage.DEPLOY_AND_REGISTER.value

    # seams exercised: state persisted, gate prompts emailed, agents audited.
    assert r.datastore.get_record("req-1:state")["build_manifest"] is not None
    assert any(m.kind == "gate_prompt" for m in r.emailer.outbox)
    agents_called = {e["agent"] for e in r.datastore.events if e["event"] == "agent_call"}
    assert {"stack-check", "triage-recommender", "build-agent", "functional-qa",
            "security-vulnerabilities", "security-governance"} <= agents_called


# == build needs_input pause + resume ========================================
def test_build_needs_input_pauses_then_resumes():
    gateway = FakeModelGateway({
        **_analysis_script(),
        "build-agent": [_ro("build/B5_needs_input.yaml"), _ro("build/B1_code_complete.yaml")],
        "functional-qa": [_ro("functional_qa/Q1_code_pass.yaml")],
        "security-vulnerabilities": [_ro("security_vuln/SV2_clean.yaml")],
        "security-governance": [_ro("security_gov/SG1_findings.yaml")],
    })
    r = _runner(gateway)
    r.advance()
    r.resume_gate_1a(Gate1aDecision.DEEP_DIVE, selected_options=("opt_001",))
    step = r.resume_gate_1b(approved=True)
    assert step.kind == "awaiting_build_input" and step.payload["questions"]

    step = r.provide_build_answers({"q1": "yes", "q2": "weekly"})
    assert step.kind == "awaiting_gate" and step.stage == Stage.GATE_2.value
    assert r.resume_gate_2(accepted=True).stage == Stage.DEPLOY_AND_REGISTER.value


# == route_elsewhere accepted at Gate 1a terminates ==========================
def test_route_elsewhere_accept_terminates():
    gateway = FakeModelGateway({
        "triage-recommender": [_ro("triage/T1_route_elsewhere.yaml")],
        "cost-estimation-rom": [_ro("rom/R2_build_ai.yaml")],
    })
    r = _runner(gateway)
    step = r.advance()
    assert step.stage == Stage.GATE_1A.value

    step = r.resume_gate_1a(Gate1aDecision.ACCEPT)
    assert step.kind == "terminal" and step.stage == Stage.TERMINATED.value


# == a High finding routes to Director adjudication, then clears ==============
def test_high_finding_routes_to_director_then_clears():
    gateway = FakeModelGateway({
        **_analysis_script(),
        "build-agent": [_ro("build/B1_code_complete.yaml")],
        "functional-qa": [_ro("functional_qa/Q1_code_pass.yaml")],
        "security-vulnerabilities": [_ro("security_vuln/SV1_findings.yaml")],  # High + Low
        "security-governance": [_ro("security_gov/SG1_findings.yaml")],        # Medium
    })
    r = _runner(gateway)
    r.advance()
    r.resume_gate_1a(Gate1aDecision.DEEP_DIVE, selected_options=("opt_001",))
    step = r.resume_gate_1b(approved=True)
    assert step.kind == "awaiting_security_adjudication"

    step = r.resume_security_adjudication(cleared=True)
    assert step.kind == "awaiting_gate" and step.stage == Stage.GATE_2.value
