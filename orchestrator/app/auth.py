"""Local username/password auth for the AI Enabler (initial, pre-SSO).

For local/dev use until the move to production team systems (SSO). Only the
AI Enabler — the decision authority (gates 1a/1b/2, security adjudication, R&D
sign-off) — signs in. Requestors are guests: they log requests without an account
and leave contact info, so no requestor role exists here.

Credentials come from the AUTH_USERS env var (no real secrets in code); a local
dev default is used only when AUTH_USERS is unset. The session is a signed cookie
(Starlette SessionMiddleware), so the web layer stays stateless and Connect-safe.
"""

from __future__ import annotations

import hmac
import os
from dataclasses import asdict, dataclass

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from .templating import templates

AI_ENABLER = "ai_enabler"
ROLES = {AI_ENABLER}

# Local dev only. Production MUST set AUTH_USERS; this is an obvious placeholder.
_DEV_DEFAULT_USERS = "enabler:enabler:ai_enabler:AI Enabler"


@dataclass(frozen=True)
class User:
    username: str
    display_name: str
    role: str

    @property
    def is_enabler(self) -> bool:
        return self.role == AI_ENABLER


def _parse_users(spec: str) -> dict[str, tuple[str, User]]:
    """'user:password:role[:display],...' -> {username: (password, User)}."""
    out: dict[str, tuple[str, User]] = {}
    for entry in spec.split(","):
        parts = [p.strip() for p in entry.split(":")]
        if len(parts) < 3 or parts[2] not in ROLES:
            continue
        username, password, role = parts[0], parts[1], parts[2]
        display = parts[3] if len(parts) > 3 and parts[3] else username
        out[username] = (password, User(username=username, display_name=display, role=role))
    return out


def load_users() -> dict[str, tuple[str, User]]:
    return _parse_users(os.environ.get("AUTH_USERS") or _DEV_DEFAULT_USERS)


def authenticate(username: str, password: str) -> User | None:
    record = load_users().get(username)
    if record and hmac.compare_digest(record[0], password):
        return record[1]
    return None


def current_user(request: Request) -> User | None:
    data = request.session.get("user")
    return User(**data) if data else None


def require_enabler(request: Request) -> User:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    if not user.is_enabler:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="AI Enabler role required")
    return user


router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"user": None, "error": error})


@router.post("/login")
def login_submit(
    request: Request, username: str = Form(""), password: str = Form("")
) -> RedirectResponse:
    user = authenticate(username, password)
    if user is None:
        return RedirectResponse(url="/login?error=1", status_code=303)
    request.session["user"] = asdict(user)
    return RedirectResponse(url="/requests", status_code=303)


@router.get("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
