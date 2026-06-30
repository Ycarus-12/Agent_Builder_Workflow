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
from app.shiny_ui import head, header  # noqa: E402

services = build_services()

app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.input_action_button("refresh", "Refresh", class_="btn btn-primary"),
        ui.output_ui("error_banner"),
        ui.input_select("request", "Requests", choices={}),
        width=330,
    ),
    head(),
    header("AI Enabler console"),
    ui.div(ui.output_ui("detail"), class_="wrap"),
    title="Tool-Request Console",
    padding=0,
)


def server(input, output, session):
    refresh = reactive.value(0)

    @reactive.calc
    def summaries():
        refresh()
        try:
            return {"data": list_summaries(services), "error": None}
        except Exception as exc:  # datastore/config error — surface, don't crash
            return {"data": [], "error": str(exc)}

    @render.ui
    def error_banner():
        err = summaries()["error"]
        if err:
            return ui.div(ui.tags.b("Can't reach the datastore. "), err, class_="errbox")
        return None

    @reactive.effect
    def _populate():
        data = summaries()["data"]
        choices = {s.request_id: f"{s.request_title} — {s.status.replace('_', ' ')}" for s in data}
        current = input.request()
        ui.update_select("request", choices=choices, selected=current if current in choices else None)

    @reactive.effect
    @reactive.event(input.refresh)
    def _do_refresh():
        refresh.set(refresh() + 1)

    @render.ui
    def detail():
        refresh()
        rid = input.request()
        if not rid:
            return ui.div(ui.p(ui.tags.em("Select a request from the left."), class_="muted"), class_="card")
        try:
            d = request_detail(services, rid)
        except Exception as exc:
            return ui.div(ui.div(ui.tags.b("Error loading request. "), str(exc), class_="errbox"), class_="card")
        step, contact = d["step"], d["contact"]
        head_bits = [ui.h1(d["title"]),
                     ui.p(ui.span(step.kind.replace("_", " "), class_=f"pill {step.kind}"),
                          ui.span(f"  stage: {step.stage}  ·  {rid}", class_="muted"))]
        if contact:
            head_bits.append(ui.p(ui.tags.b("Requestor: "),
                                  f"{contact.get('name', '')}  ·  {contact.get('email', '')}", class_="muted"))
        return ui.div(*head_bits, ui.div(*_controls(step), class_="card"))

    @reactive.effect
    @reactive.event(input.submit_decision)
    def _decide():
        rid = input.request()
        if not rid:
            return
        try:
            step = request_detail(services, rid)["step"]
            _dispatch(input, services, rid, step)
        except Exception as exc:
            ui.notification_show(f"Decision failed: {exc}", type="error", duration=10)
            return
        refresh.set(refresh() + 1)


def _controls(step):
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
            ui.input_action_button("submit_decision", "Submit decision", class_="btn btn-primary"),
        ]
    if kind == "awaiting_gate" and stage == "gate_1b":
        return [ui.tags.pre(str(step.payload.get("deepdive"))),
                ui.input_radio_buttons("g1b", "Spend", {"approve": "Approve", "decline": "Decline"}),
                ui.input_text("rationale", "Rationale"),
                ui.input_action_button("submit_decision", "Submit", class_="btn btn-primary")]
    if kind == "awaiting_gate" and stage == "gate_2":
        return [ui.tags.pre(str(step.payload.get("security"))),
                ui.input_radio_buttons("g2", "Acceptance", {"accept": "Accept & deploy", "reject": "Reject — back to build"}),
                ui.input_text("rationale", "Rationale"),
                ui.input_action_button("submit_decision", "Submit", class_="btn btn-primary")]
    if kind == "awaiting_security_adjudication":
        return [ui.tags.pre(str(step.payload.get("summary"))),
                ui.input_radio_buttons("sec", "Adjudication", {"clear": "Clear — proceed", "block": "Block — back to build"}),
                ui.input_text("rationale", "Rationale"),
                ui.input_action_button("submit_decision", "Submit", class_="btn btn-primary")]
    if kind == "awaiting_rnd_signoff":
        return [ui.tags.pre(str(step.payload.get("summary"))),
                ui.p("Heavy/sensitive work — R&D security sign-off required."),
                ui.input_action_button("submit_decision", "Record R&D sign-off", class_="btn btn-primary")]
    if kind == "awaiting_build_input":
        widgets = []
        for i, q in enumerate(step.payload.get("questions", [])):
            label = q.get("question") if isinstance(q, dict) else str(q)
            widgets.append(ui.input_text_area(f"q{i}", label, rows=2))
        widgets.append(ui.input_action_button("submit_decision", "Send answers", class_="btn btn-primary"))
        return widgets
    if kind == "terminal":
        return [ui.p(f"Complete — reached {step.stage}. No further action.")]
    return [ui.p(ui.tags.em(f"No decision pending ({kind})."), class_="muted")]


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
