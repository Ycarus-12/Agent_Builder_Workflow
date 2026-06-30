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
    pipeline_runner_after_intake,
    rehydrate_runner,
)
from .intake import ConversationSession
from .notifications import notify_submitted, notify_terminal
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
    data = services.datastore.get_record(_session_key(request_id)) or {"turns": []}
    status = None
    if snapshot is not None:
        status = {"stage": snapshot.get("pipeline", {}).get("stage"),
                  "status": _status_for(snapshot.get("pipeline", {}))}
    return {"turns": data.get("turns", []), "finalized": snapshot is not None, "status": status}


def submit_message(services: Services, request_id: str, message: str) -> dict[str, Any]:
    data = services.datastore.get_record(_session_key(request_id))
    if data is None:
        return intake_view(services, request_id)
    session = ConversationSession.from_dict(data)
    runner = make_intake_runner(services, request_id=request_id)

    result = runner.submit_turn(session, message)
    services.datastore.store_record(_session_key(request_id), session.to_dict())

    if result.marker.fired:
        outcome = runner.finalize(session, Pipeline(), date=date.today().isoformat())
        pipeline_runner_after_intake(services, outcome, request_id=request_id).advance()
        notify_submitted(services, request_id, services.datastore.get_record(contact_key(request_id)))

    return intake_view(services, request_id)


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
