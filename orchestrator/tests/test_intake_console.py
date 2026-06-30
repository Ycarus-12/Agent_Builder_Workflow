"""Requestor intake page: a conversation reaches sign-off, the record is extracted,
and the request surfaces in the Director console — all over stateless HTTP turns."""

import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.api import app
from app.composition import build_services
from app.console import get_services
from app.ports.chat import ChatTurn, ToolCall

_FIX = Path(__file__).resolve().parents[1] / "evals" / "fixtures"


def _ro(rel: str) -> str:
    out = yaml.safe_load((_FIX / rel).read_text(encoding="utf-8"))["recorded_output"]
    return out if isinstance(out, str) else json.dumps(out)


def _extract_internal() -> str:
    rec = json.loads(_ro("extraction/E1_rich.yaml"))
    rec["data_sensitivity"] = "internal"
    return json.dumps(rec)


def _triage_build_light() -> str:
    t = json.loads(_ro("triage/T6_build.yaml"))
    t["options"][0]["weight"] = "light"
    return json.dumps(t)


@pytest.fixture()
def client():
    svc = build_services("offline")
    gw = svc.gateway
    gw.script("intake-conversation", [
        "What problem are you solving?",
        "Got it — auto-create the checklist on deal close.\n\n[[INTAKE_SIGNOFF_CONFIRMED]]",
    ])
    gw.script("intake-extraction", [_extract_internal()])
    gw.script_chat("stack-check", [ChatTurn(tool_calls=[ToolCall("c1", "emit_finding", json.loads(_ro("stack_check/S3_empty.yaml")))])])
    gw.script("triage-recommender", [_triage_build_light()])
    gw.script("cost-estimation-rom", [_ro("rom/R2_build_ai.yaml")])
    app.dependency_overrides[get_services] = lambda: svc
    c = TestClient(app)
    c.post("/login", data={"username": "requestor", "password": "requestor"})  # Requestor session
    yield c
    app.dependency_overrides.clear()


def test_intake_start_page_renders(client):
    r = client.get("/intake")
    assert r.status_code == 200
    assert "Start a tool request" in r.text


def test_conversation_to_signoff_creates_a_request(client):
    # start -> get a request id from the redirect
    r = client.post("/intake/start", data={"requestor": "J. Rivera", "team": "PS"}, follow_redirects=False)
    assert r.status_code == 303
    request_id = r.headers["location"].rsplit("/", 1)[-1]

    # chat view renders, not yet finalized
    assert "Intake conversation" in client.get(f"/intake/{request_id}").text

    # first turn: no marker -> still chatting
    client.post(f"/intake/{request_id}/message", data={"message": "I need a checklist zap."}, follow_redirects=False)
    view = client.get(f"/intake/{request_id}").text
    assert "Send" in view and "submitted" not in view

    # second turn: marker fires -> finalized + driven into analysis
    client.post(f"/intake/{request_id}/message", data={"message": "Yes, that's correct."}, follow_redirects=False)
    done = client.get(f"/intake/{request_id}").text
    assert "submitted" in done.lower()

    # the requestor can track it in "my requests", awaiting Gate 1a
    listing = client.get("/my-requests").text
    assert request_id in listing
    assert "awaiting gate" in listing
