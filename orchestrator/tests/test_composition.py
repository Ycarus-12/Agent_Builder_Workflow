"""Composition root: offline builds fakes, live builds real adapters (no network),
and live fails fast when a seam is unconfigured."""

import pytest

from app.composition import (
    CompositionError,
    Services,
    build_services,
    make_pipeline_runner,
)
from app.pipeline_runner import PipelineRunner, RunState
from app.ports import (
    AirtableDatastore,
    FakeModelGateway,
    InMemoryDatastore,
    InMemoryEmailer,
    ResendEmailer,
)
from app.ports.gateway import OpenRouterGateway
from app.state_machine import Pipeline

_LIVE_ENV = {
    "OPENROUTER_API_KEY": "or_test",
    "AIRTABLE_API_KEY": "pat_test",
    "AIRTABLE_BASE_ID": "appXYZ",
    "RESEND_API_KEY": "re_test",
    "RESEND_FROM": "bot@acme.test",
}


def test_offline_builds_all_fakes():
    svc = build_services("offline")
    assert isinstance(svc.gateway, FakeModelGateway)
    assert isinstance(svc.datastore, InMemoryDatastore)
    assert isinstance(svc.emailer, InMemoryEmailer)
    assert svc.audit.datastore is svc.datastore  # audit writes to the same store


def test_default_mode_is_offline(monkeypatch):
    monkeypatch.delenv("ORCHESTRATOR_MODE", raising=False)
    assert build_services().mode == "offline"


def test_live_builds_real_adapters_without_network(monkeypatch):
    for k, v in _LIVE_ENV.items():
        monkeypatch.setenv(k, v)
    svc = build_services("live")
    assert isinstance(svc.gateway, OpenRouterGateway)
    assert isinstance(svc.datastore, AirtableDatastore)
    assert isinstance(svc.emailer, ResendEmailer)


def test_live_fails_fast_when_unconfigured(monkeypatch):
    for k in _LIVE_ENV:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(CompositionError):
        build_services("live")


def test_unknown_mode_rejected():
    with pytest.raises(CompositionError, match="unknown"):
        build_services("staging")


def test_per_seam_gateway_live_with_offline_storage(monkeypatch):
    # The common local setup: real OpenRouter, in-memory datastore/email.
    for k in ("AIRTABLE_API_KEY", "AIRTABLE_BASE_ID", "RESEND_API_KEY", "RESEND_FROM"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or_test")
    monkeypatch.setenv("GATEWAY_MODE", "live")
    svc = build_services("offline")
    assert isinstance(svc.gateway, OpenRouterGateway)
    assert isinstance(svc.datastore, InMemoryDatastore)
    assert isinstance(svc.emailer, InMemoryEmailer)


def test_per_seam_unknown_value_rejected(monkeypatch):
    monkeypatch.setenv("GATEWAY_MODE", "sometimes")
    with pytest.raises(CompositionError, match="GATEWAY_MODE"):
        build_services("offline")


def test_make_pipeline_runner_wires_services():
    svc = build_services("offline")
    runner = make_pipeline_runner(
        svc,
        pipeline=Pipeline(),
        state=RunState(intake_record={"problem": "x"}, transcript="t"),
        request_id="req-1",
    )
    assert isinstance(runner, PipelineRunner)
    assert runner.gateway is svc.gateway
    assert runner.datastore is svc.datastore
    assert runner.emailer is svc.emailer
