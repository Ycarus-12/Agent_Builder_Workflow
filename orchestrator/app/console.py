"""Director gate console — server-rendered HTML over the orchestrator.

The web layer holds no runner between requests: every page rehydrates a runner
from the datastore (composition.rehydrate_runner), reads or applies a decision,
and lets the runner re-persist. Deploys as one FastAPI app to Posit Connect; the
Resend gate emails link here. Identity/auth is fronted by Connect — `decided_by`
is captured per decision, defaulting to "Director".
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .composition import Services, build_services, current_mode, rehydrate_runner
from .request_store import RequestStore
from .state_machine import Gate1aDecision

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

router = APIRouter()


@lru_cache(maxsize=1)
def _cached_services() -> Services:
    return build_services(current_mode())


def get_services() -> Services:
    """FastAPI dependency; overridable in tests via app.dependency_overrides."""
    return _cached_services()


@router.get("/", response_class=HTMLResponse)
def index() -> RedirectResponse:
    return RedirectResponse(url="/requests", status_code=303)


@router.get("/requests", response_class=HTMLResponse)
def list_requests(request: Request, services: Services = Depends(get_services)) -> HTMLResponse:
    summaries = RequestStore(services.datastore).summaries()
    return _TEMPLATES.TemplateResponse(request, "requests.html", {"summaries": summaries})


@router.get("/requests/{request_id}", response_class=HTMLResponse)
def request_detail(
    request_id: str, request: Request, services: Services = Depends(get_services)
) -> HTMLResponse:
    runner = rehydrate_runner(services, request_id)
    step = runner.current_step()
    title = (runner.state.intake_record or {}).get("request_title", request_id)
    return _TEMPLATES.TemplateResponse(
        request, "request_detail.html",
        {"request_id": request_id, "step": step, "title": title},
    )


def _redirect(request_id: str) -> RedirectResponse:
    return RedirectResponse(url=f"/requests/{request_id}", status_code=303)


@router.post("/requests/{request_id}/gate1a")
def decide_gate_1a(
    request_id: str,
    decision: str = Form(...),
    selected_options: str = Form(""),
    rationale: str = Form(""),
    decided_by: str = Form("Director"),
    services: Services = Depends(get_services),
) -> RedirectResponse:
    runner = rehydrate_runner(services, request_id)
    selected = tuple(o.strip() for o in selected_options.split(",") if o.strip())
    runner.resume_gate_1a(
        Gate1aDecision(decision), selected_options=selected, decided_by=decided_by, rationale=rationale,
    )
    return _redirect(request_id)


@router.post("/requests/{request_id}/gate1b")
def decide_gate_1b(
    request_id: str,
    approved: str = Form(...),
    rationale: str = Form(""),
    decided_by: str = Form("Director"),
    services: Services = Depends(get_services),
) -> RedirectResponse:
    runner = rehydrate_runner(services, request_id)
    runner.resume_gate_1b(approved=_truthy(approved), decided_by=decided_by, rationale=rationale)
    return _redirect(request_id)


@router.post("/requests/{request_id}/gate2")
def decide_gate_2(
    request_id: str,
    accepted: str = Form(...),
    rationale: str = Form(""),
    decided_by: str = Form("Director"),
    services: Services = Depends(get_services),
) -> RedirectResponse:
    runner = rehydrate_runner(services, request_id)
    runner.resume_gate_2(accepted=_truthy(accepted), decided_by=decided_by, rationale=rationale)
    return _redirect(request_id)


@router.post("/requests/{request_id}/build-input")
async def answer_build_input(
    request_id: str, request: Request, services: Services = Depends(get_services)
) -> RedirectResponse:
    form = await request.form()
    answers = {k: str(v) for k, v in form.items() if k != "decided_by"}
    runner = rehydrate_runner(services, request_id)
    runner.provide_build_answers(answers)
    return _redirect(request_id)


@router.post("/requests/{request_id}/security")
def adjudicate_security(
    request_id: str,
    cleared: str = Form(...),
    rationale: str = Form(""),
    decided_by: str = Form("Director"),
    services: Services = Depends(get_services),
) -> RedirectResponse:
    runner = rehydrate_runner(services, request_id)
    runner.resume_security_adjudication(cleared=_truthy(cleared), decided_by=decided_by, rationale=rationale)
    return _redirect(request_id)


@router.post("/requests/{request_id}/rnd-signoff")
def record_rnd_signoff(
    request_id: str, services: Services = Depends(get_services)
) -> RedirectResponse:
    rehydrate_runner(services, request_id).record_rnd_signoff()
    return _redirect(request_id)


def _truthy(value: str) -> bool:
    return value.strip().lower() in ("true", "yes", "1", "approve", "accept", "clear")
