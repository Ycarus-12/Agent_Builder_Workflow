"""Shiny glue logic: responsive intake (turn vs. finalize split), the zero-cost
demo seed, and console decisions to deploy — same backend, no Shiny runtime."""

import json
from pathlib import Path

import yaml

from app.composition import build_services
from app.ports.chat import ChatTurn, ToolCall
from app.request_store import contact_key
from app.shiny_logic import (
    apply_decision,
    finalize_request,
    intake_view,
    list_summaries,
    request_detail,
    seed_demo_request,
    start_intake,
    submit_turn_only,
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
    gw.script("intake-conversation", ["What problem are you solving?", "Got it.\n\n[[INTAKE_SIGNOFF_CONFIRMED]]"])
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


def test_intake_turn_then_finalize_then_console_to_deploy():
    svc = _services()
    rid = start_intake(svc, name="Jane", email="jane@co.test", team="PS")

    assert submit_turn_only(svc, rid, "I need a checklist zap.")["marker_fired"] is False
    assert submit_turn_only(svc, rid, "Yes, that's right.")["marker_fired"] is True

    # sign-off is responsive: the request isn't finalized until finalize_request runs
    assert intake_view(svc, rid)["finalized"] is False
    finalize_request(svc, rid)
    view = intake_view(svc, rid)
    assert view["finalized"] and view["status"]["status"] == "awaiting_gate"
    assert view["requestor_name"] == "Jane"  # chat labels use the provided name

    assert rid in [s.request_id for s in list_summaries(svc)]
    assert request_detail(svc, rid)["step"].stage == "gate_1a"
    assert apply_decision(svc, rid, kind="gate_1a", decision="deep_dive", selected_options="opt_001").stage == "gate_1b"
    assert apply_decision(svc, rid, kind="gate_1b", approved=True).stage == "gate_2"
    assert apply_decision(svc, rid, kind="gate_2", accepted=True).kind == "terminal"

    kinds = [m.kind for m in svc.emailer.outbox]
    assert "requestor_submitted" in kinds and "requestor_outcome" in kinds


def test_demo_seed_lands_at_gate_1a_with_no_model_calls():
    svc = build_services("offline")  # no gateway scripts at all
    rid = seed_demo_request(svc)
    assert rid.startswith("demo-")
    assert rid in [s.request_id for s in list_summaries(svc)]
    detail = request_detail(svc, rid)
    assert detail["step"].stage == "gate_1a"
    assert detail["contact"]["name"] == "Demo User"
    assert svc.gateway.calls == []  # the seed cost zero model calls
