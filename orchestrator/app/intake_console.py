"""Requestor intake page + "my requests" tracking.

A stateless chat: each message rehydrates the ConversationSession from the
datastore, runs one intake-conversation turn, and re-persists. On the sign-off
marker it finalizes (extraction -> stored record) and kicks the request into
analysis, after which it surfaces in the AI Enabler console. Any signed-in user
may start a request; the request is tagged with its owner so the requestor can
track their own via /my-requests.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .auth import User, require_user
from .composition import Services, make_intake_runner, pipeline_runner_after_intake
from .console import get_services
from .intake import ConversationSession
from .ports.identity import RequestorIdentity
from .request_store import RequestStore, owner_key
from .state_machine import Pipeline
from .templating import templates

router = APIRouter()


def _session_key(request_id: str) -> str:
    return f"{request_id}:intake_session"


@router.get("/my-requests", response_class=HTMLResponse)
def my_requests(
    request: Request, user: User = Depends(require_user), services: Services = Depends(get_services)
) -> HTMLResponse:
    summaries = RequestStore(services.datastore).summaries(owner=user.username)
    return templates.TemplateResponse(request, "my_requests.html", {"summaries": summaries, "user": user})


@router.get("/intake", response_class=HTMLResponse)
def intake_start(request: Request, user: User = Depends(require_user)) -> HTMLResponse:
    return templates.TemplateResponse(request, "intake_start.html", {"user": user})


@router.post("/intake/start")
def intake_create(
    request: Request, team: str = Form(""),
    user: User = Depends(require_user), services: Services = Depends(get_services),
) -> RedirectResponse:
    request_id = "req-" + uuid.uuid4().hex[:8]
    session = ConversationSession(
        session_id=request_id,
        identity=RequestorIdentity(requestor=user.display_name, team=team or "Unknown"),
    )
    services.datastore.store_record(_session_key(request_id), session.to_dict())
    services.datastore.store_record(owner_key(request_id), {"owner": user.username})
    return RedirectResponse(url=f"/intake/{request_id}", status_code=303)


@router.get("/intake/{request_id}", response_class=HTMLResponse)
def intake_view(
    request_id: str, request: Request,
    user: User = Depends(require_user), services: Services = Depends(get_services),
) -> HTMLResponse:
    finalized = services.datastore.get_record(f"{request_id}:snapshot") is not None
    data = services.datastore.get_record(_session_key(request_id)) or {"turns": []}
    return templates.TemplateResponse(
        request, "intake_chat.html",
        {"request_id": request_id, "turns": data.get("turns", []), "finalized": finalized, "user": user},
    )


@router.post("/intake/{request_id}/message")
def intake_message(
    request_id: str, message: str = Form(...),
    user: User = Depends(require_user), services: Services = Depends(get_services),
) -> RedirectResponse:
    data = services.datastore.get_record(_session_key(request_id))
    if data is None:
        return RedirectResponse(url="/intake", status_code=303)
    session = ConversationSession.from_dict(data)
    runner = make_intake_runner(services, request_id=request_id)

    result = runner.submit_turn(session, message)
    services.datastore.store_record(_session_key(request_id), session.to_dict())

    if result.marker.fired:
        outcome = runner.finalize(session, Pipeline(), date=date.today().isoformat())
        pipeline_runner_after_intake(services, outcome, request_id=request_id).advance()

    return RedirectResponse(url=f"/intake/{request_id}", status_code=303)
