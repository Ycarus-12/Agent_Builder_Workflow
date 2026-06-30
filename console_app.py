"""AI Enabler gate console — Shiny for Python app for Posit Connect Cloud.

Deploy this content RESTRICTED to the AI Enabler's account — Connect handles the
login (no app-level auth). Lists in-flight requests and applies decisions at each
stop (gates 1a/1b/2, build input, security adjudication, R&D sign-off). Backend is
reused unchanged; interaction logic lives in app.shiny_logic.

Connect publish: Framework = Shiny, Primary file = console_app.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "orchestrator"))

from shiny import App, reactive, render, ui  # noqa: E402

from app.composition import build_services  # noqa: E402
from app.shiny_logic import apply_decision, list_summaries, request_detail  # noqa: E402

services = build_services()

_POSIT_HEAD = ui.tags.head(
    ui.tags.link(rel="stylesheet", href="https://fonts.bunny.net/css?family=open-sans:300,400,600,700"),
    ui.tags.style(
        ":root{--bs-primary:#447099;--bs-link-color:#447099;}"
        "body{font-family:'Open Sans',system-ui,sans-serif;}"
        ".btn-primary{background-color:#447099;border-color:#447099;}"
        "h1,h2,h3{font-weight:300;}"
    ),
)

app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.input_action_button("refresh", "Refresh", class_="btn-primary"),
        ui.output_ui("request_list"),
        width=320,
    ),
    _POSIT_HEAD,
    ui.h2("AI Enabler console"),
    ui.output_ui("detail"),
    title="Tool-Request Console",
)


def server(input, output, session):
    selected = reactive.value(None)
    refresh = reactive.value(0)

    @reactive.calc
    def summaries():
        refresh()
        return list_summaries(services)

    @render.ui
    def request_list():
        rows = []
        for s in summaries():
            label = f"{s.request_title} — {s.status.replace('_', ' ')}"
            rows.append(ui.input_action_link(f"pick_{s.request_id}", label))
            rows.append(ui.br())
        return ui.div(ui.h4("Requests"), *(rows or [ui.p("No requests yet.")]))

    # One observer per request id to set the selection when its link is clicked.
    @reactive.effect
    def _wire_picks():
        for s in summaries():
            _bind_pick(input, selected, s.request_id)

    @render.ui
    def detail():
        refresh()
        rid = selected()
        if not rid:
            return ui.p(ui.tags.em("Select a request from the left."))
        d = request_detail(services, rid)
        step, contact = d["step"], d["contact"]
        head = [ui.h3(d["title"]),
                ui.p(ui.tags.b(step.kind.replace("_", " ")), f" · stage: {step.stage} · {rid}")]
        if contact:
            head.append(ui.p(f"Requestor: {contact.get('name', '')} · {contact.get('email', '')}"))
        return ui.div(*head, ui.hr(), *_controls(step))

    @reactive.effect
    @reactive.event(input.submit_decision)
    def _decide():
        rid = selected()
        if not rid:
            return
        step = request_detail(services, rid)["step"]
        _dispatch(input, services, rid, step)
        refresh.set(refresh() + 1)


def _bind_pick(input, selected, request_id: str):
    @reactive.effect
    @reactive.event(input[f"pick_{request_id}"])
    def _():
        selected.set(request_id)


def _controls(step):
    """Inputs + a shared submit button for the pending decision."""
    kind, stage = step.kind, step.stage
    if kind == "awaiting_gate" and stage == "gate_1a":
        opts = step.payload.get("options", [])
        rec = step.payload.get("recommendation", {})
        return [
            ui.p(ui.tags.b("Triage recommends: "), rec.get("outcome", "")),
            ui.tags.ul(*[ui.tags.li(f"{o.get('option_id')} — {o.get('label')} [{o.get('route')}]") for o in opts]),
            ui.input_select("g1a_decision", "Decision",
                            {"deep_dive": "Deep-dive selected", "accept": "Accept", "reject": "Reject — re-triage"}),
            ui.input_text("g1a_opts", "Selected option ids (comma-separated)", placeholder="opt_001"),
            ui.input_text("rationale", "Rationale"),
            ui.input_action_button("submit_decision", "Submit decision", class_="btn-primary"),
        ]
    if kind == "awaiting_gate" and stage == "gate_1b":
        return [ui.tags.pre(str(step.payload.get("deepdive"))),
                ui.input_radio_buttons("g1b", "Spend", {"approve": "Approve", "decline": "Decline"}),
                ui.input_text("rationale", "Rationale"),
                ui.input_action_button("submit_decision", "Submit", class_="btn-primary")]
    if kind == "awaiting_gate" and stage == "gate_2":
        return [ui.tags.pre(str(step.payload.get("security"))),
                ui.input_radio_buttons("g2", "Acceptance", {"accept": "Accept & deploy", "reject": "Reject — back to build"}),
                ui.input_text("rationale", "Rationale"),
                ui.input_action_button("submit_decision", "Submit", class_="btn-primary")]
    if kind == "awaiting_security_adjudication":
        return [ui.tags.pre(str(step.payload.get("summary"))),
                ui.input_radio_buttons("sec", "Adjudication", {"clear": "Clear — proceed", "block": "Block — back to build"}),
                ui.input_text("rationale", "Rationale"),
                ui.input_action_button("submit_decision", "Submit", class_="btn-primary")]
    if kind == "awaiting_rnd_signoff":
        return [ui.tags.pre(str(step.payload.get("summary"))),
                ui.p("Heavy/sensitive work — R&D security sign-off required."),
                ui.input_action_button("submit_decision", "Record R&D sign-off", class_="btn-primary")]
    if kind == "awaiting_build_input":
        qs = step.payload.get("questions", [])
        widgets = []
        for i, q in enumerate(qs):
            label = q.get("question") if isinstance(q, dict) else str(q)
            widgets.append(ui.input_text_area(f"q{i}", label, rows=2))
        widgets.append(ui.input_action_button("submit_decision", "Send answers", class_="btn-primary"))
        return widgets
    if kind == "terminal":
        return [ui.p(f"Complete — reached {step.stage}. No further action.")]
    return [ui.p(ui.tags.em(f"No decision pending ({kind})."))]


def _dispatch(input, services, rid, step):
    kind, stage = step.kind, step.stage
    if kind == "awaiting_gate" and stage == "gate_1a":
        apply_decision(services, rid, kind="gate_1a", decision=input.g1a_decision(),
                       selected_options=input.g1a_opts(), rationale=input.rationale() or "")
    elif kind == "awaiting_gate" and stage == "gate_1b":
        apply_decision(services, rid, kind="gate_1b", approved=(input.g1b() == "approve"),
                       rationale=input.rationale() or "")
    elif kind == "awaiting_gate" and stage == "gate_2":
        apply_decision(services, rid, kind="gate_2", accepted=(input.g2() == "accept"),
                       rationale=input.rationale() or "")
    elif kind == "awaiting_security_adjudication":
        apply_decision(services, rid, kind="security", cleared=(input.sec() == "clear"),
                       rationale=input.rationale() or "")
    elif kind == "awaiting_rnd_signoff":
        apply_decision(services, rid, kind="rnd_signoff")
    elif kind == "awaiting_build_input":
        answers = {f"q{i}": input[f"q{i}"]() for i in range(len(step.payload.get("questions", [])))}
        apply_decision(services, rid, kind="build_input", answers=answers)


app = App(app_ui, server)
