"""Local username/password auth + roles: login required, role gating, and a
requestor sees only their own requests."""

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
from app.request_store import owner_key
from app.state_machine import Pipeline

_FIX = Path(__file__).resolve().parents[1] / "evals" / "fixtures"


def _ro(rel: str) -> str:
    out = yaml.safe_load((_FIX / rel).read_text(encoding="utf-8"))["recorded_output"]
    return out if isinstance(out, str) else json.dumps(out)


def _seed_request(svc, request_id, owner, title):
    gw = svc.gateway
    t = json.loads(_ro("triage/T6_build.yaml")); t["options"][0]["weight"] = "light"
    gw.script_chat("stack-check", [ChatTurn(tool_calls=[ToolCall("c1", "emit_finding", json.loads(_ro("stack_check/S3_empty.yaml")))])])
    gw.script("triage-recommender", [json.dumps(t)])
    gw.script("cost-estimation-rom", [_ro("rom/R2_build_ai.yaml")])
    p = Pipeline(); p.requestor_signoff(); p.extraction_complete(); p.data_sensitivity = DataSensitivity.INTERNAL
    state = RunState(intake_record={"request_title": title, "data_sensitivity": "internal", "acceptance_criteria": []}, transcript="t")
    make_pipeline_runner(svc, pipeline=p, state=state, request_id=request_id).advance()
    svc.datastore.store_record(owner_key(request_id), {"owner": owner})


@pytest.fixture()
def svc():
    s = build_services("offline")
    app.dependency_overrides[get_services] = lambda: s
    yield s
    app.dependency_overrides.clear()


def _client():
    return TestClient(app)


def test_unauthenticated_redirected_to_login(svc):
    c = _client()
    r = c.get("/requests", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_bad_credentials_rejected(svc):
    c = _client()
    r = c.post("/login", data={"username": "enabler", "password": "wrong"}, follow_redirects=False)
    assert r.status_code == 303 and "error" in r.headers["location"]


def test_requestor_cannot_reach_enabler_console(svc):
    c = _client()
    c.post("/login", data={"username": "requestor", "password": "requestor"})
    assert c.get("/requests").status_code == 403


def test_enabler_reaches_console(svc):
    c = _client()
    c.post("/login", data={"username": "enabler", "password": "enabler"})
    assert c.get("/requests").status_code == 200


def test_requestor_sees_only_own_requests(svc):
    _seed_request(svc, "req-mine", owner="requestor", title="Mine")
    _seed_request(svc, "req-theirs", owner="someone_else", title="Theirs")
    c = _client()
    c.post("/login", data={"username": "requestor", "password": "requestor"})
    body = c.get("/my-requests").text
    assert "Mine" in body
    assert "Theirs" not in body


def test_login_routes_role_to_landing_page(svc):
    c = _client()
    r = c.post("/login", data={"username": "requestor", "password": "requestor"}, follow_redirects=False)
    assert r.headers["location"] == "/my-requests"
    c.get("/logout")
    r = c.post("/login", data={"username": "enabler", "password": "enabler"}, follow_redirects=False)
    assert r.headers["location"] == "/requests"
