"""Guest intake — the public conversational capture front end.

Requestors are guests: no login. They provide contact info, then describe the
problem in a stateless chat (each message rehydrates the ConversationSession,
runs one intake-conversation turn, and re-persists). On the sign-off marker it
finalizes (extraction -> stored record) and kicks the request into analysis,
after which it surfaces in the AI Enabler console with the contact info attached.
The per-request URL (unguessable id) doubles as the guest's status/tracking page.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .composition import Services, make_intake_runner, pipeline_runner_after_intake
from .console import get_services
from .intake import ConversationSession
from .notifications import notify_submitted
from .ports.identity import RequestorIdentity
from .request_store import contact_key
from .state_machine import Pipeline
from .templating import templates

router = APIRouter()


def _session_key(request_id: str) -> str:
    return f"{request_id}:intake_session"


@router.get("/intake", response_class=HTMLResponse)
def intake_start(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "intake_start.html", {"user": None})


@router.post("/intake/start")
def intake_create(
    name: str = Form(""), email: str = Form(""), team: str = Form(""),
    services: Services = Depends(get_services),
) -> RedirectResponse:
    request_id = "req-" + uuid.uuid4().hex[:8]
    session = ConversationSession(
        session_id=request_id,
        identity=RequestorIdentity(requestor=name or "Guest", team=team or "Unknown"),
    )
    services.datastore.store_record(_session_key(request_id), session.to_dict())
    services.datastore.store_record(
        contact_key(request_id),
        {"name": name or "Guest", "email": email, "team": team or "Unknown"},
    )
    return RedirectResponse(url=f"/intake/{request_id}", status_code=303)


@router.get("/intake/{request_id}", response_class=HTMLResponse)
def intake_view(request_id: str, request: Request, services: Services = Depends(get_services)) -> HTMLResponse:
    snapshot = services.datastore.get_record(f"{request_id}:snapshot")
    data = services.datastore.get_record(_session_key(request_id)) or {"turns": []}
    status = None
    if snapshot is not None:
        from .request_store import _status_for

        status = {"stage": snapshot.get("pipeline", {}).get("stage"),
                  "status": _status_for(snapshot.get("pipeline", {}))}
    return templates.TemplateResponse(
        request, "intake_chat.html",
        {"request_id": request_id, "turns": data.get("turns", []),
         "finalized": snapshot is not None, "status": status, "user": None},
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
        outcome = runner.finalize(session, Pipeline(), date=date.today().isoformat())
        pipeline_runner_after_intake(services, outcome, request_id=request_id).advance()
        # Confirm receipt to the guest (best-effort; never blocks the flow).
        contact = services.datastore.get_record(contact_key(request_id))
        notify_submitted(services, request_id, contact)

    return RedirectResponse(url=f"/intake/{request_id}", status_code=303)
