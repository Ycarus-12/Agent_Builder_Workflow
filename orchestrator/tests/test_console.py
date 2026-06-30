"""Director gate console: the HTML pages render, and posting decisions drives the
pipeline through to deploy — each request rehydrated from the datastore."""

import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.api import app
from app.composition import build_services, make_pipeline_runner
from app.console import get_services
from app.enums import DataSensitivity
from app.pipeline_runner import RunState
from app.ports.chat import ChatTurn, ToolCall
from app.state_machine import Pipeline

_FIX = Path(__file__).resolve().parents[1] / "evals" / "fixtures"


def _ro(rel: str) -> str:
    out = yaml.safe_load((_FIX / rel).read_text(encoding="utf-8"))["recorded_output"]
    return out if isinstance(out, str) else json.dumps(out)


def _triage_build_light() -> str:
    t = json.loads(_ro("triage/T6_build.yaml"))
    t["options"][0]["weight"] = "light"
    return json.dumps(t)


def _seed_request_at_gate_1a():
    svc = build_services("offline")
    gw = svc.gateway
    gw.script_chat("stack-check", [ChatTurn(tool_calls=[ToolCall("c1", "emit_finding", json.loads(_ro("stack_check/S3_empty.yaml")))])])
    gw.script("triage-recommender", [_triage_build_light()])
    gw.script("cost-estimation-rom", [_ro("rom/R2_build_ai.yaml")])
    gw.script("cost-estimation-deepdive", [_ro("deepdive/D3_build_vs_buy_n2.yaml")])
    gw.script("build-agent", [_ro("build/B1_code_complete.yaml")])
    gw.script("functional-qa", [_ro("functional_qa/Q1_code_pass.yaml")])
    gw.script("security-vulnerabilities", [_ro("security_vuln/SV2_clean.yaml")])
    gw.script("security-governance", [_ro("security_gov/SG1_findings.yaml")])
    p = Pipeline()
    p.requestor_signoff()
    p.extraction_complete()
    p.data_sensitivity = DataSensitivity.INTERNAL
    state = RunState(
        intake_record={"request_title": "Deal checklist", "problem": "p", "data_sensitivity": "internal", "acceptance_criteria": []},
        transcript="Requestor: hi",
    )
    make_pipeline_runner(svc, pipeline=p, state=state, request_id="req-1").advance()  # -> gate_1a
    return svc


@pytest.fixture()
def client():
    svc = _seed_request_at_gate_1a()
    app.dependency_overrides[get_services] = lambda: svc
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_request_list_renders(client):
    r = client.get("/requests")
    assert r.status_code == 200
    assert "Deal checklist" in r.text
    assert "req-1" in r.text


def test_detail_shows_gate_1a(client):
    r = client.get("/requests/req-1")
    assert r.status_code == 200
    assert "Gate 1a" in r.text
    assert "opt_001" in r.text


def test_posting_decisions_drives_to_deploy(client):
    # Gate 1a: deep-dive the recommended option
    r = client.post("/requests/req-1/gate1a",
                    data={"decision": "deep_dive", "selected_options": "opt_001", "rationale": "looks strong"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert "gate_1b" in client.get("/requests/req-1").text

    # Gate 1b: approve spend -> runs build/qa/security -> lands at gate_2
    assert client.post("/requests/req-1/gate1b", data={"approved": "true"}, follow_redirects=False).status_code == 303
    assert "Gate 2" in client.get("/requests/req-1").text

    # Gate 2: accept -> deploy
    assert client.post("/requests/req-1/gate2", data={"accepted": "true"}, follow_redirects=False).status_code == 303
    detail = client.get("/requests/req-1")
    assert "Complete" in detail.text and "deploy_and_register" in detail.text


def test_unknown_request_errors(client):
    # No snapshot for this id -> rehydrate raises (surfaced as a 500 by the app).
    with pytest.raises(Exception):
        client.get("/requests/nope")
