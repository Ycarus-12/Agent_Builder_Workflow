"""Glue between the Shiny UIs and the orchestrator backend.

Pure functions (given a Services bundle) so the interaction logic is unit-tested
without a Shiny runtime — the Shiny app files are thin event wiring on top. Mirrors
what the FastAPI console/intake handlers do; the backend (runner, store,
notifications) is unchanged.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from .composition import (
    Services,
    make_intake_runner,
    make_pipeline_runner,
    pipeline_runner_after_intake,
    rehydrate_runner,
)
from .enums import DataSensitivity, Outcome
from .intake import ConversationSession
from .notifications import notify_submitted, notify_terminal
from .pipeline_runner import RunState
from .ports.identity import RequestorIdentity
from .request_store import RequestStore, _status_for, contact_key
from .state_machine import Gate1aDecision, Pipeline


def _session_key(request_id: str) -> str:
    return f"{request_id}:intake_session"


# == intake (guest) ==========================================================
def start_intake(services: Services, *, name: str, email: str, team: str) -> str:
    request_id = "req-" + uuid.uuid4().hex[:8]
    session = ConversationSession(
        session_id=request_id,
        identity=RequestorIdentity(requestor=name or "Guest", team=team or "Unknown"),
    )
    services.datastore.store_record(_session_key(request_id), session.to_dict())
    services.datastore.store_record(
        contact_key(request_id), {"name": name or "Guest", "email": email, "team": team or "Unknown"}
    )
    return request_id


def intake_view(services: Services, request_id: str) -> dict[str, Any]:
    snapshot = services.datastore.get_record(f"{request_id}:snapshot")
    data = services.datastore.get_record(_session_key(request_id)) or {}
    status = None
    if snapshot is not None:
        status = {"stage": snapshot.get("pipeline", {}).get("stage"),
                  "status": _status_for(snapshot.get("pipeline", {}))}
    name = (data.get("identity") or {}).get("requestor")
    if not name:
        contact = services.datastore.get_record(contact_key(request_id)) or {}
        name = contact.get("name", "You")
    return {"turns": data.get("turns", []), "finalized": snapshot is not None,
            "status": status, "requestor_name": name}


def submit_turn_only(services: Services, request_id: str, message: str) -> dict[str, Any]:
    """Run ONE conversation turn and persist the session. No finalize/analysis —
    so the chat stays responsive; finalize_request() handles the heavy work."""
    data = services.datastore.get_record(_session_key(request_id))
    if data is None:
        return {"turns": [], "marker_fired": False}
    session = ConversationSession.from_dict(data)
    runner = make_intake_runner(services, request_id=request_id)
    result = runner.submit_turn(session, message)
    services.datastore.store_record(_session_key(request_id), session.to_dict())
    return {"turns": [list(t) for t in session.turns], "marker_fired": result.marker.fired}


def finalize_request(services: Services, request_id: str) -> None:
    """Extraction + analysis to the first gate. Heavy (model calls) — run in a
    background thread so sign-off shows the confirmation immediately."""
    data = services.datastore.get_record(_session_key(request_id))
    if data is None:
        return
    session = ConversationSession.from_dict(data)
    runner = make_intake_runner(services, request_id=request_id)
    outcome = runner.finalize(session, Pipeline(), date=date.today().isoformat())
    pipeline_runner_after_intake(services, outcome, request_id=request_id).advance()
    notify_submitted(services, request_id, services.datastore.get_record(contact_key(request_id)))


# == admin demo: seed a testable request at Gate 1a, with NO AI cost ==========
_DEMO_RECORD = {
    "request_title": "Auto-create onboarding checklist on deal close",
    "problem_outcome": "When a CRM deal closes, the owner rebuilds the same onboarding "
                       "checklist by hand. They want it created automatically.",
    "data_sensitivity": "internal",
    "systems_involved": ["CRM", "work-management tool"],
    "acceptance_criteria": [
        "Checklist is auto-created when a deal is marked closed-won",
        "The deal owner is notified",
        "Each run is logged",
    ],
}
_DEMO_TRANSCRIPT = (
    "Demo User: After every CRM deal closes I rebuild the same onboarding checklist by hand.\n"
    "Scout: Got it — what should happen automatically when a deal closes?\n"
    "Demo User: Auto-create the checklist and notify the owner.\n"
    "Scout: Here's the problem statement and acceptance criteria — happy to sign off?\n"
    "Demo User: Yes, that's right."
)
_DEMO_TRIAGE = {
    "request_title": _DEMO_RECORD["request_title"],
    "options": [{
        "option_id": "opt_001", "route": "build", "label": "Automation that builds the checklist",
        "summary": "On deal close, create the checklist in the work tool and notify the owner.",
        "tool_name": None, "capability_id": None, "avenue": "code", "engine": "ai",
        "weight": "light", "vendor_or_category": None, "bought_capability": None,
    }],
    "recommendation": {"outcome": "build", "recommended_option_id": "opt_001",
                       "rationale": "No existing coverage; a small automation fits.",
                       "risks": [], "destination_team": None, "alternatives": []},
}
_DEMO_ROM = {"options": [{"option_id": "opt_001", "effort_band": "S", "run_cost_band": "low"}]}
_DEMO_STACK = {"matches": [], "registry_confidence": "high", "no_existing_coverage": True}


def seed_demo_request(services: Services) -> str:
    """Seed a request positioned at Gate 1a with canned analysis — zero model cost.
    Lets the console be tested end-to-end cheaply; proceeding past Gate 1b uses real AI."""
    request_id = "demo-" + uuid.uuid4().hex[:8]
    services.datastore.store_record(
        contact_key(request_id), {"name": "Demo User", "email": "demo@example.com", "team": "Testing"})
    services.datastore.store_record(
        _session_key(request_id),
        ConversationSession(session_id=request_id,
                            identity=RequestorIdentity("Demo User", "Testing")).to_dict())

    p = Pipeline()
    p.requestor_signoff()
    p.extraction_complete()            # -> analysis:stack_check
    p.data_sensitivity = DataSensitivity.INTERNAL
    p.advance_analysis()               # -> triage
    p.set_triage_recommendation(Outcome.BUILD)
    p.advance_analysis()               # -> cost_rom
    p.advance_analysis()               # -> gate_1a
    state = RunState(intake_record=_DEMO_RECORD, transcript=_DEMO_TRANSCRIPT,
                     stack_check_finding=_DEMO_STACK, triage_output=_DEMO_TRIAGE, rom_output=_DEMO_ROM)
    runner = make_pipeline_runner(services, pipeline=p, state=state, request_id=request_id)
    runner._persist()                  # store snapshot + index, no agent calls
    return request_id


# == console (AI Enabler) ====================================================
def list_summaries(services: Services):
    return RequestStore(services.datastore).summaries()


def request_detail(services: Services, request_id: str) -> dict[str, Any]:
    runner = rehydrate_runner(services, request_id)
    step = runner.current_step()
    title = (runner.state.intake_record or {}).get("request_title", request_id)
    contact = RequestStore(services.datastore).contact_of(request_id)
    return {"step": step, "title": title, "contact": contact}


def apply_decision(
    services: Services, request_id: str, *, kind: str, decided_by: str = "AI Enabler", **params
):
    """Dispatch a console decision to the matching resume_*; notify on terminal."""
    runner = rehydrate_runner(services, request_id)
    if kind == "gate_1a":
        selected = tuple(o.strip() for o in str(params.get("selected_options", "")).split(",") if o.strip())
        step = runner.resume_gate_1a(
            Gate1aDecision(params["decision"]), selected_options=selected,
            decided_by=decided_by, rationale=params.get("rationale", ""),
        )
    elif kind == "gate_1b":
        step = runner.resume_gate_1b(approved=bool(params["approved"]), decided_by=decided_by,
                                     rationale=params.get("rationale", ""))
    elif kind == "gate_2":
        step = runner.resume_gate_2(accepted=bool(params["accepted"]), decided_by=decided_by,
                                    rationale=params.get("rationale", ""))
    elif kind == "build_input":
        step = runner.provide_build_answers(params.get("answers", {}))
    elif kind == "security":
        step = runner.resume_security_adjudication(cleared=bool(params["cleared"]), decided_by=decided_by,
                                                   rationale=params.get("rationale", ""))
    elif kind == "rnd_signoff":
        step = runner.record_rnd_signoff()
    else:
        raise ValueError(f"unknown decision kind {kind!r}")
    notify_terminal(services, request_id, step)
    return step
