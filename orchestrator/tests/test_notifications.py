"""Email wiring: AI Enabler gate prompts and guest submission/outcome notices flow
through the Emailer seam (InMemoryEmailer offline), and failures never break a run."""

import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.api import app
from app.composition import build_services, make_pipeline_runner
from app.console import get_services
from app.enums import DataSensitivity
from app.notifications import notify_outcome, notify_submitted, notify_terminal
from app.pipeline_runner import PipelineStep, RunState
from app.ports.chat import ChatTurn, ToolCall
from app.request_store import contact_key
from app.state_machine import Pipeline, Stage

_FIX = Path(__file__).resolve().parents[1] / "evals" / "fixtures"


def _ro(rel: str) -> str:
    out = yaml.safe_load((_FIX / rel).read_text(encoding="utf-8"))["recorded_output"]
    return out if isinstance(out, str) else json.dumps(out)


def _kinds(svc):
    return [m.kind for m in svc.emailer.outbox]


# -- unit: requestor notices --------------------------------------------------
def test_submitted_and_outcome_notices():
    svc = build_services("offline")
    contact = {"name": "Jane", "email": "jane@co.test", "team": "PS"}
    notify_submitted(svc, "req-1", contact)
    notify_outcome(svc, "req-1", contact, accepted=True)
    notify_outcome(svc, "req-1", contact, accepted=False)
    sent = svc.emailer.outbox
    assert [m.to for m in sent] == ["jane@co.test"] * 3
    assert _kinds(svc) == ["requestor_submitted", "requestor_outcome", "requestor_outcome"]
    assert "accepted" in sent[1].body and "closed" in sent[2].body


def test_no_email_without_contact_address():
    svc = build_services("offline")
    notify_submitted(svc, "req-1", {"name": "NoEmail"})
    notify_terminal(svc, "req-1", PipelineStep(kind="awaiting_gate", stage="gate_1a"))
    assert svc.emailer.outbox == []


def test_notify_terminal_picks_outcome_by_stage():
    svc = build_services("offline")
    svc.datastore.store_record(contact_key("req-1"), {"name": "J", "email": "j@co.test"})
    notify_terminal(svc, "req-1", PipelineStep(kind="terminal", stage=Stage.DEPLOY_AND_REGISTER.value))
    notify_terminal(svc, "req-1", PipelineStep(kind="terminal", stage=Stage.TERMINATED.value))
    assert _kinds(svc) == ["requestor_outcome", "requestor_outcome"]
    assert "accepted" in svc.emailer.outbox[0].body
    assert "closed" in svc.emailer.outbox[1].body


def test_email_failure_never_breaks_the_run():
    class _Boom:
        def send(self, **_):
            raise RuntimeError("provider down")

    svc = build_services("offline")
    svc.emailer = _Boom()
    notify_submitted(svc, "req-1", {"name": "J", "email": "j@co.test"})  # must not raise
    assert any(e.get("event") == "email_error" for e in svc.datastore.events)


# -- gate prompts go to the AI Enabler ---------------------------------------
def test_gate_prompt_emails_the_ai_enabler():
    svc = build_services("offline")
    gw = svc.gateway
    t = json.loads(_ro("triage/T6_build.yaml")); t["options"][0]["weight"] = "light"
    gw.script_chat("stack-check", [ChatTurn(tool_calls=[ToolCall("c1", "emit_finding", json.loads(_ro("stack_check/S3_empty.yaml")))])])
    gw.script("triage-recommender", [json.dumps(t)])
    gw.script("cost-estimation-rom", [_ro("rom/R2_build_ai.yaml")])
    p = Pipeline(); p.requestor_signoff(); p.extraction_complete(); p.data_sensitivity = DataSensitivity.INTERNAL
    state = RunState(intake_record={"request_title": "Checklist", "data_sensitivity": "internal", "acceptance_criteria": []}, transcript="t")
    make_pipeline_runner(svc, pipeline=p, state=state, request_id="req-1").advance()  # -> gate_1a
    prompts = [m for m in svc.emailer.outbox if m.kind == "gate_prompt"]
    assert prompts and prompts[0].to == "ai-enabler@example.com"
    assert "/requests/req-1" in prompts[0].body
