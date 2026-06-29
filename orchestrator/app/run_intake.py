"""CLI to drive an intake session end-to-end — the "prove the loop" entrypoint.

Modes:
  --fake                 Fully offline demo on the FakeModelGateway (canned turns +
                         a canned valid IntakeRecord). Runs anywhere; proves wiring.
  (default, live)        OpenRouterGateway; requires OPENROUTER_API_KEY. Interactive
                         stdin unless --scripted is given.
  --scripted FILE        Replay requestor turns (one per line) instead of stdin.

Usage:
  python -m app.run_intake --fake
  OPENROUTER_API_KEY=... python -m app.run_intake --requestor "J. Rivera" --team "PS"
  OPENROUTER_API_KEY=... python -m app.run_intake --scripted turns.txt
"""

from __future__ import annotations

import argparse
import json
import sys

from .agents import load_intake_conversation_spec, load_intake_extraction_spec
from .config import load_gateway_config
from .logging_audit import AuditLog
from .ports.datastore import InMemoryDatastore
from .ports.gateway import FakeModelGateway, ModelGateway, OpenRouterGateway
from .ports.identity import RequestorIdentity
from .runtime import IntakeRunner
from .state_machine import Pipeline

_FAKE_CONVERSATION = [
    "Thanks! Tell me about the problem you're trying to solve.",
    "Got it — so closing a deal currently means building the kickoff checklist by hand.\n\n"
    "Here's what I captured: a recurring manual step after each deal close. "
    "Does that look right?",
    "Great — I've recorded your sign-off.\n\n[[INTAKE_SIGNOFF_CONFIRMED]]",
]
_FAKE_RECORD = json.dumps(
    {
        "requestor": "J. Rivera", "team": "Professional Services", "date": "2026-06-29",
        "request_title": "Auto-create kickoff checklist on deal close",
        "problem_outcome": "Eliminate the manual kickoff checklist built after every deal close.",
        "current_workaround": "Building the checklist by hand in the work tool.",
        "success_criteria": "Checklist auto-created and owner notified when a deal closes.",
        "frequency": "a few times a week", "who_is_affected": "requestor",
        "time_cost": "~20 min each", "deadline": None,
        "systems_involved": ["CRM", "work-management tool"],
        "data_sensitivity": "internal", "customer_facing": False,
        "solution_idea": "A Zapier-style automation", "attachments": [],
        "context_constraints_nuance": None,
        "acceptance_criteria": ["auto-create checklist", "notify owner", "log each run"],
        "transcript_reference": "txn/2026-06-29/req-cli",
    }
)


def _build_gateway(use_fake: bool) -> tuple[ModelGateway, str]:
    if use_fake:
        gw = FakeModelGateway(
            {"intake-conversation": list(_FAKE_CONVERSATION), "intake-extraction": [_FAKE_RECORD]}
        )
        return gw, "fake"
    config = load_gateway_config()
    if not config.has_key:
        sys.exit("OPENROUTER_API_KEY is not set; use --fake for an offline demo.")
    models = {
        "intake-conversation": (config.conversation_model, config.conversation_max_tokens),
        "intake-extraction": (config.extraction_model, config.extraction_max_tokens),
    }
    return OpenRouterGateway(config, models), "openrouter"


def _requestor_turns(args) -> "list[str] | None":
    if args.scripted:
        with open(args.scripted, encoding="utf-8") as fh:
            return [line.rstrip("\n") for line in fh if line.strip()]
    if args.fake:
        # Three requestor turns; the fake agent fires the marker on its 3rd response.
        return [
            "I need a Zapier zap.",
            "Every time a deal closes I build the kickoff checklist by hand.",
            "Yes, that's correct.",
        ]
    return None  # interactive


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Drive an intake session end-to-end.")
    parser.add_argument("--fake", action="store_true", help="offline demo on the fake gateway")
    parser.add_argument("--scripted", help="file of requestor turns, one per line")
    parser.add_argument("--requestor", default="Test User")
    parser.add_argument("--team", default="Test Team")
    parser.add_argument("--date", default="2026-06-29")
    parser.add_argument("--request-id", default="req-cli")
    parser.add_argument("--session-id", default="cli-session")
    args = parser.parse_args(argv)

    gateway, which = _build_gateway(args.fake)
    store = InMemoryDatastore()  # shared by the runner and its audit log
    runner = IntakeRunner(
        gateway=gateway,
        datastore=store,
        audit=AuditLog(store),
        conversation_spec=load_intake_conversation_spec(),
        extraction_spec=load_intake_extraction_spec(),
        request_id=args.request_id,
    )
    identity = RequestorIdentity(requestor=args.requestor, team=args.team)
    session = runner.open_session(args.session_id, identity)
    pipeline = Pipeline()
    print(f"[intake] gateway={which} requestor={identity.requestor} team={identity.team}\n")

    scripted = _requestor_turns(args)
    scripted_iter = iter(scripted) if scripted is not None else None

    while True:
        if scripted_iter is not None:
            try:
                message = next(scripted_iter)
            except StopIteration:
                print("[intake] scripted turns exhausted without a sign-off marker.")
                return 1
            print(f"requestor> {message}")
        else:
            try:
                message = input("requestor> ").strip()
            except EOFError:
                print("\n[intake] input closed without a sign-off marker.")
                return 1
            if not message:
                continue

        result = runner.submit_turn(session, message)
        print(f"agent> {result.visible_reply}\n")
        if result.marker.is_misuse:
            print(f"[intake] marker misuse ignored: {result.marker.misuse}\n")
        if result.marker.fired:
            outcome = runner.finalize(session, pipeline, date=args.date)
            print("[intake] sign-off confirmed; extraction complete.\n")
            print(f"[intake] transcript_reference: {outcome.transcript_reference}")
            print(f"[intake] pipeline stage: {pipeline.stage.value}")
            print("[intake] IntakeRecord:\n" + json.dumps(outcome.record, indent=2))
            return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
