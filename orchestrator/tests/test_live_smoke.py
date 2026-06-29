"""Live smoke test — a REAL model call through the OpenRouter gateway.

Skipped unless OPENROUTER_API_KEY is set, so CI (which has no key, and the
dev/test sanitized-data rule) stays green. Run locally with a key to prove the
loop against a live model:

    OPENROUTER_API_KEY=... pytest tests/test_live_smoke.py -q
"""

import os

import pytest
from jsonschema import Draft202012Validator

from app.agents import (
    intake_record_schema,
    load_intake_conversation_spec,
    load_intake_extraction_spec,
)
from app.config import load_gateway_config
from app.logging_audit import AuditLog
from app.ports.datastore import InMemoryDatastore
from app.ports.gateway import OpenRouterGateway
from app.ports.identity import RequestorIdentity
from app.runtime import IntakeRunner
from app.state_machine import Pipeline

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="no OPENROUTER_API_KEY; live smoke test skipped",
)

# A sanitized, synthetic transcript — no real customer data (dev/test rule).
SCRIPTED_TURNS = [
    "Every time a deal closes in our CRM I build a kickoff checklist by hand in our "
    "work tool. Takes about 20 minutes, a few times a week, just me.",
    "Success would be the checklist auto-created and the owner notified when a deal "
    "closes. No customer PII is involved, just internal project fields.",
    "Yes, that's correct — please confirm.",
]


def test_live_intake_produces_schema_valid_record():
    config = load_gateway_config()
    models = {
        "intake-conversation": (config.conversation_model, config.conversation_max_tokens),
        "intake-extraction": (config.extraction_model, config.extraction_max_tokens),
    }
    gateway = OpenRouterGateway(config, models)
    store = InMemoryDatastore()
    runner = IntakeRunner(
        gateway=gateway,
        datastore=store,
        audit=AuditLog(store),
        conversation_spec=load_intake_conversation_spec(),
        extraction_spec=load_intake_extraction_spec(),
        request_id="live-1",
    )
    session = runner.open_session("live-session", RequestorIdentity("Test User", "Test Team"))
    pipeline = Pipeline()

    outcome = None
    for turn in SCRIPTED_TURNS:
        result = runner.submit_turn(session, turn)
        if result.marker.fired:
            outcome = runner.finalize(session, pipeline, date="2026-06-29")
            break

    assert outcome is not None, "live model did not fire the sign-off marker"
    Draft202012Validator(intake_record_schema()).validate(outcome.record)
