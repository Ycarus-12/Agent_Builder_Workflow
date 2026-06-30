"""Requestor intake page — the conversational capture front end.

A stateless chat: each message rehydrates the ConversationSession from the
datastore, runs one intake-conversation turn, and re-persists. On the sign-off
marker it finalizes (extraction -> stored record) and kicks the request into
analysis, after which it surfaces in the Director console. Shares the wired
services and templates with the gate console.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .composition import Services, make_intake_runner, pipeline_runner_after_intake
from .console import _TEMPLATES, get_services
from .intake import ConversationSession
from .ports.identity import RequestorIdentity
from .state_machine import Pipeline

router = APIRouter()


def _session_key(request_id: str) -> str:
    return f"{request_id}:intake_session"


@router.get("/intake", response_class=HTMLResponse)
def intake_start(request: Request) -> HTMLResponse:
    return _TEMPLATES.TemplateResponse(request, "intake_start.html", {})


@router.post("/intake/start")
def intake_create(
    requestor: str = Form(""), team: str = Form(""), services: Services = Depends(get_services)
) -> RedirectResponse:
    request_id = "req-" + uuid.uuid4().hex[:8]
    session = ConversationSession(
        session_id=request_id,
        identity=RequestorIdentity(requestor=requestor or "Requestor", team=team or "Unknown"),
    )
    services.datastore.store_record(_session_key(request_id), session.to_dict())
    return RedirectResponse(url=f"/intake/{request_id}", status_code=303)


@router.get("/intake/{request_id}", response_class=HTMLResponse)
def intake_view(
    request_id: str, request: Request, services: Services = Depends(get_services)
) -> HTMLResponse:
    finalized = services.datastore.get_record(f"{request_id}:snapshot") is not None
    data = services.datastore.get_record(_session_key(request_id)) or {"turns": []}
    return _TEMPLATES.TemplateResponse(
        request, "intake_chat.html",
        {"request_id": request_id, "turns": data.get("turns", []), "finalized": finalized},
    )


@router.post("/intake/{request_id}/message")
def intake_message(
    request_id: str, message: str = Form(...), services: Services = Depends(get_services)
) -> RedirectResponse:
    data = services.datastore.get_record(_session_key(request_id))
    if data is None:
        return RedirectResponse(url="/intake", status_code=303)
    session = ConversationSession.from_dict(data)
    runner = make_intake_runner(services, request_id=request_id)

    result = runner.submit_turn(session, message)
    services.datastore.store_record(_session_key(request_id), session.to_dict())

    if result.marker.fired:
        # Sign-off: extract the record, then drive analysis to the first gate so the
        # request appears for the Director.
        outcome = runner.finalize(session, Pipeline(), date=date.today().isoformat())
        pipeline_runner_after_intake(services, outcome, request_id=request_id).advance()

    return RedirectResponse(url=f"/intake/{request_id}", status_code=303)
