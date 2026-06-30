"""Guest intake: no login, contact info captured, conversation to sign-off, and the
request then appears for the AI Enabler with the contact attached."""

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
def svc():
    s = build_services("offline")
    gw = s.gateway
    gw.script("intake-conversation", [
        "What problem are you solving?",
        "Got it — auto-create the checklist on deal close.\n\n[[INTAKE_SIGNOFF_CONFIRMED]]",
    ])
    gw.script("intake-extraction", [_extract_internal()])
    gw.script_chat("stack-check", [ChatTurn(tool_calls=[ToolCall("c1", "emit_finding", json.loads(_ro("stack_check/S3_empty.yaml")))])])
    gw.script("triage-recommender", [_triage_build_light()])
    gw.script("cost-estimation-rom", [_ro("rom/R2_build_ai.yaml")])
    app.dependency_overrides[get_services] = lambda: s
    yield s
    app.dependency_overrides.clear()


def test_intake_is_public(svc):
    # No login required to reach intake.
    assert TestClient(app).get("/intake").status_code == 200


def test_guest_request_to_signoff_then_visible_to_enabler(svc):
    guest = TestClient(app)
    # start as a guest with contact info
    r = guest.post("/intake/start",
                   data={"name": "Jane Rivera", "email": "jane@co.test", "team": "PS"},
                   follow_redirects=False)
    assert r.status_code == 303
    request_id = r.headers["location"].rsplit("/", 1)[-1]

    guest.post(f"/intake/{request_id}/message", data={"message": "I need a checklist zap."}, follow_redirects=False)
    guest.post(f"/intake/{request_id}/message", data={"message": "Yes, that's correct."}, follow_redirects=False)

    # guest status page (public, by unguessable id) shows submitted + a status pill
    status_page = guest.get(f"/intake/{request_id}").text
    assert "submitted" in status_page.lower()
    assert "awaiting gate" in status_page

    # the AI Enabler sees it with the guest's contact info
    enabler = TestClient(app)
    enabler.post("/login", data={"username": "enabler", "password": "enabler"})
    listing = enabler.get("/requests").text
    assert request_id in listing and "jane@co.test" in listing


def test_guest_cannot_reach_enabler_console(svc):
    assert TestClient(app).get("/requests", follow_redirects=False).status_code == 303  # -> /login
