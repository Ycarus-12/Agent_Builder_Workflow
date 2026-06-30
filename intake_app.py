"""Public guest intake — Shiny for Python app for Posit Connect Cloud.

No login (deploy this content as public). Guests leave contact info and chat with
"Scout" (the intake agent); on sign-off the request is captured and analysis runs
in the background, so the confirmation screen (with a saveable status URL) appears
immediately. ?request=<id> reopens a saved request; ?demo=1 reveals an admin
"seed test request" button (no AI cost).

Connect publish: Framework = Shiny, Primary file = intake_app.py
"""

import os
import sys
import threading
from urllib.parse import parse_qs

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "orchestrator"))

from shiny import App, reactive, render, ui  # noqa: E402

from app.composition import build_services  # noqa: E402
from app.shiny_logic import (  # noqa: E402
    finalize_request, intake_view, seed_demo_request, start_intake, submit_turn_only,
)
from app.shiny_ui import head, header  # noqa: E402

services = build_services()

app_ui = ui.page_fluid(
    head(),
    header("Request a tool"),
    ui.div(ui.output_ui("main"), class_="wrap"),
    padding=0,
)


def server(input, output, session):
    request_id = reactive.value(None)
    submitted = reactive.value(False)
    refresh = reactive.value(0)

    def _query() -> dict:
        try:
            return parse_qs((session.clientdata.url_search() or "").lstrip("?"))
        except Exception:
            return {}

    def _self_url(rid: str) -> str:
        try:
            cd = session.clientdata
            proto, host = cd.url_protocol() or "https:", cd.url_hostname() or ""
            port, path = cd.url_port() or "", cd.url_pathname() or "/"
            base = f"{proto}//{host}" + (f":{port}" if port else "") + path
            return f"{base}?request={rid}"
        except Exception:
            return f"?request={rid}"

    @reactive.effect
    def _from_url():
        if request_id() is not None:
            return
        rid = (_query().get("request") or [None])[0]
        if rid:
            request_id.set(rid)
            submitted.set(True)  # reopening a saved request -> show its status

    @render.ui
    def main():
        refresh()
        rid = request_id()
        if rid is None:
            return _start_form(demo=bool(_query().get("demo")))
        if submitted():
            return _confirmation(rid, _self_url(rid))
        return _chat(rid)

    # -- handlers --------------------------------------------------------
    @reactive.effect
    @reactive.event(input.begin)
    def _begin():
        try:
            rid = start_intake(services, name=input.name(), email=input.email(), team=input.team())
        except Exception as exc:
            ui.notification_show(f"Couldn't start: {exc}", type="error", duration=10)
            return
        request_id.set(rid)

    @reactive.effect
    @reactive.event(input.send)
    def _send():
        msg = (input.message() or "").strip()
        if not msg:
            return
        try:
            result = submit_turn_only(services, request_id(), msg)
        except Exception as exc:
            ui.notification_show(f"Something went wrong: {exc}", type="error", duration=10)
            return
        if result["marker_fired"]:
            # Sign-off: show confirmation now; do the heavy extraction+analysis in the background.
            rid = request_id()
            threading.Thread(target=finalize_request, args=(services, rid), daemon=True).start()
            submitted.set(True)
        refresh.set(refresh() + 1)

    @reactive.effect
    @reactive.event(input.run_demo)
    def _run_demo():
        try:
            rid = seed_demo_request(services)
        except Exception as exc:
            ui.notification_show(f"Demo seed failed: {exc}", type="error", duration=10)
            return
        request_id.set(rid)
        submitted.set(True)

    @reactive.effect
    @reactive.event(input.refresh_status)
    def _refresh_status():
        refresh.set(refresh() + 1)

    # -- views -----------------------------------------------------------
    def _start_form(demo: bool):
        demo_block = ui.div(
            ui.hr(),
            ui.p(ui.tags.small("Admin / testing")),
            ui.input_action_button("run_demo", "Seed a test request (no AI cost)", class_="btn btn-outline-secondary"),
        ) if demo else None
        return ui.div(
            ui.h1("Start a tool request"),
            ui.p("Leave your contact info, then describe the problem in a short chat with Scout. "
                 "Intake captures the request — it never decides. No account needed.", class_="muted"),
            ui.div(
                ui.input_text("name", "Your name", placeholder="Jane Rivera"),
                ui.input_text("email", "Email (so we can follow up)", placeholder="jane@company.com"),
                ui.input_text("team", "Team (optional)", placeholder="Professional Services"),
                ui.input_action_button("begin", "Begin intake", class_="btn btn-primary"),
                demo_block,
                class_="card",
            ),
        )

    def _chat(rid: str):
        view = intake_view(services, rid)
        name = view["requestor_name"] or "You"
        bubbles = []
        for role, content in view["turns"]:
            who = name if role == "requestor" else "Scout"
            bubbles.append(ui.div(ui.span(who, class_="who"), content, class_=f"bubble {role}"))
        return ui.div(
            ui.h1("Chat with Scout"),
            ui.div(*bubbles, class_="card") if bubbles else None,
            ui.div(
                ui.input_text_area("message", "Your message", rows=3,
                                   placeholder="Describe the problem you're trying to solve..."),
                ui.input_action_button("send", "Send", class_="btn btn-primary"),
                class_="card",
            ),
        )

    def _confirmation(rid: str, url: str):
        view = intake_view(services, rid)
        st = view["status"]
        if st:
            status_line = ui.p("Current status: ", ui.span(st["status"].replace("_", " "), class_=f"pill {st['status']}"),
                               ui.span(f"  ({st['stage']})", class_="muted"))
        else:
            status_line = ui.p(ui.span("processing", class_="pill running"),
                               ui.span("  analysis is running — check back in a moment.", class_="muted"))
        return ui.div(
            ui.h1("Request submitted ✓"),
            ui.div(
                ui.p("Thanks — your request has been captured and is being reviewed by the AI Enabler. "
                     "We'll follow up using the contact info you provided."),
                status_line,
                ui.h3("Save this link to check your request"),
                ui.div(url, class_="urlbox"),
                ui.input_action_button("refresh_status", "Refresh status", class_="btn btn-outline-secondary"),
                class_="card",
            ),
        )


app = App(app_ui, server)
