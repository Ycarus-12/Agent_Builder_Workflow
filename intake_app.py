"""Public guest intake — Shiny for Python app for Posit Connect Cloud.

No login (deploy this content as public). Guests leave contact info and describe
the problem in a chat; on sign-off the request is captured and enters analysis,
surfacing in the AI Enabler console. Backend (orchestrator) is reused unchanged;
the interaction logic lives in app.shiny_logic.

Connect publish: Framework = Shiny, Primary file = intake_app.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "orchestrator"))

from shiny import App, reactive, render, ui  # noqa: E402

from app.composition import build_services  # noqa: E402
from app.shiny_logic import intake_view, start_intake, submit_message  # noqa: E402

services = build_services()

_POSIT_HEAD = ui.tags.head(
    ui.tags.link(rel="stylesheet", href="https://fonts.bunny.net/css?family=open-sans:300,400,600,700"),
    ui.tags.style(
        ":root{--bs-primary:#447099;--bs-link-color:#447099;}"
        "body{font-family:'Open Sans',system-ui,sans-serif;}"
        ".btn-primary{background-color:#447099;border-color:#447099;}"
        "h1,h2,h3{font-weight:300;}"
        ".bubble{padding:.5rem .8rem;border-radius:10px;margin:.3rem 0;max-width:80%;}"
        ".bubble.requestor{background:#447099;color:#fff;margin-left:auto;}"
        ".bubble.agent{background:#eef0f3;}"
    ),
)

app_ui = ui.page_fluid(
    _POSIT_HEAD,
    ui.h2("Start a tool request"),
    ui.output_ui("main"),
)


def server(input, output, session):
    request_id = reactive.value(None)
    refresh = reactive.value(0)

    @render.ui
    def main():
        refresh()
        rid = request_id()
        if rid is None:
            return ui.div(
                ui.p("Leave your contact info, then describe the problem in a short "
                     "conversation. Intake captures the request — it never decides. No account needed."),
                ui.input_text("name", "Your name", placeholder="Jane Rivera"),
                ui.input_text("email", "Email (so we can follow up)", placeholder="jane@company.com"),
                ui.input_text("team", "Team (optional)", placeholder="Professional Services"),
                ui.input_action_button("begin", "Begin intake", class_="btn-primary"),
            )

        view = intake_view(services, rid)
        bubbles = [ui.div(ui.tags.small(role), ui.br(), content, class_=f"bubble {role}")
                   for role, content in view["turns"]]
        if view["finalized"]:
            st = view["status"]
            return ui.div(
                *bubbles,
                ui.hr(),
                ui.h3("Request submitted ✓"),
                ui.p("Captured and signed off — now in review by the AI Enabler. "
                     "We'll follow up using the contact info you provided."),
                ui.p(f"Status: {st['status'].replace('_', ' ')} ({st['stage']})") if st else None,
                ui.p(ui.tags.small(f"Bookmark this page (request {rid}) to check back; the link is private to you.")),
            )
        return ui.div(
            *bubbles,
            ui.input_text_area("message", "Your message", rows=3,
                               placeholder="Describe the problem you're trying to solve..."),
            ui.input_action_button("send", "Send", class_="btn-primary"),
        )

    @reactive.effect
    @reactive.event(input.begin)
    def _begin():
        rid = start_intake(services, name=input.name(), email=input.email(), team=input.team())
        request_id.set(rid)

    @reactive.effect
    @reactive.event(input.send)
    def _send():
        msg = input.message()
        if msg and msg.strip():
            submit_message(services, request_id(), msg)
            refresh.set(refresh() + 1)


app = App(app_ui, server)
