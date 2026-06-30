"""Shiny glue logic: a guest intake reaches sign-off, surfaces in the console, and
decisions drive it to deploy — the same backend the FastAPI layer uses, no Shiny
runtime needed."""

import json
from pathlib import Path

import yaml

from app.composition import build_services
from app.ports.chat import ChatTurn, ToolCall
from app.request_store import contact_key
from app.shiny_logic import (
    apply_decision,
    intake_view,
    list_summaries,
    request_detail,
    start_intake,
    submit_message,
)

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


def _services():
    svc = build_services("offline")
    gw = svc.gateway
    gw.script("intake-conversation", [
        "What problem are you solving?",
        "Got it.\n\n[[INTAKE_SIGNOFF_CONFIRMED]]",
    ])
    gw.script("intake-extraction", [_extract_internal()])
    gw.script_chat("stack-check", [ChatTurn(tool_calls=[ToolCall("c1", "emit_finding", json.loads(_ro("stack_check/S3_empty.yaml")))])])
    gw.script("triage-recommender", [_triage_build_light()])
    gw.script("cost-estimation-rom", [_ro("rom/R2_build_ai.yaml")])
    gw.script("cost-estimation-deepdive", [_ro("deepdive/D3_build_vs_buy_n2.yaml")])
    gw.script("build-agent", [_ro("build/B1_code_complete.yaml")])
    gw.script("functional-qa", [_ro("functional_qa/Q1_code_pass.yaml")])
    gw.script("security-vulnerabilities", [_ro("security_vuln/SV2_clean.yaml")])
    gw.script("security-governance", [_ro("security_gov/SG1_findings.yaml")])
    return svc


def test_intake_to_console_to_deploy():
    svc = _services()

    rid = start_intake(svc, name="Jane", email="jane@co.test", team="PS")
    assert svc.datastore.get_record(contact_key(rid))["email"] == "jane@co.test"

    submit_message(svc, rid, "I need a checklist zap.")
    view = submit_message(svc, rid, "Yes, that's right.")  # marker -> finalize + analysis
    assert view["finalized"] and view["status"]["status"] == "awaiting_gate"

    # appears in the console list
    assert rid in [s.request_id for s in list_summaries(svc)]
    assert request_detail(svc, rid)["step"].stage == "gate_1a"

    # decisions drive it to deploy
    assert apply_decision(svc, rid, kind="gate_1a", decision="deep_dive", selected_options="opt_001").stage == "gate_1b"
    assert apply_decision(svc, rid, kind="gate_1b", approved=True).stage == "gate_2"
    final = apply_decision(svc, rid, kind="gate_2", accepted=True)
    assert final.kind == "terminal" and final.stage == "deploy_and_register"

    # guest got a submission email + an acceptance email
    kinds = [m.kind for m in svc.emailer.outbox]
    assert "requestor_submitted" in kinds and "requestor_outcome" in kinds


def test_intake_view_before_start_is_empty():
    svc = build_services("offline")
    view = intake_view(svc, "req-missing")
    assert view["turns"] == [] and view["finalized"] is False
