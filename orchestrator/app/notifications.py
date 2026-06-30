"""Requestor-facing email (Resend in live mode, the in-memory fake offline).

Guests leave contact info at intake; these send them a submission confirmation and
an outcome notice (accepted/deploying, or closed). All sends are best-effort and
audited — a down mail provider never breaks the request flow. The AI Enabler's own
gate prompts are sent by the PipelineRunner; this module covers the guest side.
"""

from __future__ import annotations

from typing import Any

from .config import console_base_url
from .request_store import RequestStore
from .state_machine import Stage


def _send(services, *, to: str, subject: str, body: str, kind: str, request_id: str) -> None:
    if not to:
        return
    try:
        services.emailer.send(to=to, subject=subject, body=body, kind=kind)
    except Exception as exc:  # provider/transport failure — record and continue
        services.audit.raw(request_id, {"event": "email_error", "kind": kind, "error": str(exc)})


def _status_link(request_id: str) -> str:
    return f"{console_base_url()}/intake/{request_id}"


def notify_submitted(services, request_id: str, contact: dict | None) -> None:
    contact = contact or {}
    _send(
        services, to=contact.get("email", ""), kind="requestor_submitted", request_id=request_id,
        subject="We received your tool request",
        body=(
            f"Hi {contact.get('name', 'there')},\n\n"
            f"Thanks — your request has been captured and signed off. It's now in review.\n"
            f"You can check its status any time here (this link is private to you):\n"
            f"{_status_link(request_id)}\n"
        ),
    )


def notify_outcome(services, request_id: str, contact: dict | None, *, accepted: bool) -> None:
    contact = contact or {}
    if accepted:
        subject = "Your tool request was approved"
        body = (
            f"Hi {contact.get('name', 'there')},\n\n"
            f"Good news — your request has been accepted and is being deployed. "
            f"We'll be in touch with next steps.\n\nStatus: {_status_link(request_id)}\n"
        )
    else:
        subject = "Update on your tool request"
        body = (
            f"Hi {contact.get('name', 'there')},\n\n"
            f"Your request has been reviewed and closed for now — we'll follow up with the "
            f"reasoning and any alternative.\n\nStatus: {_status_link(request_id)}\n"
        )
    _send(services, to=contact.get("email", ""), kind="requestor_outcome",
          request_id=request_id, subject=subject, body=body)


def notify_terminal(services, request_id: str, step: Any) -> None:
    """Send the right outcome email when a decision drives a request to a terminal."""
    if getattr(step, "kind", None) != "terminal":
        return
    contact = RequestStore(services.datastore).contact_of(request_id)
    notify_outcome(services, request_id, contact, accepted=(step.stage == Stage.DEPLOY_AND_REGISTER.value))
