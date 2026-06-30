"""Composition root — wire the seams into a runnable set of services.

One place builds the ports and selects fake vs. real per a single env switch
(`ORCHESTRATOR_MODE`): `offline` (default) runs entirely on the in-memory fakes;
`live` builds the real adapters (OpenRouter + Resend + Airtable + the registry
checkout). Live mode validates each seam's config at startup and fails fast with a
clear message — it never silently falls back to a fake for a system of record.

Application/web entrypoints call build_services() once and hand the bundle to the
runners; the runners stay seam-agnostic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .agents import load_intake_conversation_spec, load_intake_extraction_spec
from .config import (
    GatewayConfig,
    ai_enabler_email,
    load_airtable_config,
    load_emailer_config,
    load_gateway_config,
)
from .logging_audit import AuditLog
from .pipeline_runner import PipelineRunner, RunState
from .retry_loop import DEFAULT_MAX_ATTEMPTS
from .runtime import IntakeOutcome, IntakeRunner
from .ports import (
    AirtableDatastore,
    Datastore,
    Emailer,
    FakeIdentityProvider,
    FakeModelGateway,
    IdentityProvider,
    InMemoryDatastore,
    InMemoryEmailer,
    ModelGateway,
    ResendEmailer,
)
from .ports.gateway import OpenRouterGateway
from .registry.source import InMemoryRegistry, RegistrySource, default_registry_source
from .state_machine import Pipeline

MODE_ENV = "ORCHESTRATOR_MODE"
LIVE = "live"
OFFLINE = "offline"


class CompositionError(RuntimeError):
    """Raised when live mode is selected but a seam is not configured."""


@dataclass
class Services:
    """The wired seams for one process; runners receive these, not concrete tools."""

    mode: str
    gateway: ModelGateway
    datastore: Datastore
    emailer: Emailer
    registry_source: RegistrySource
    identity: IdentityProvider
    audit: AuditLog


def current_mode() -> str:
    return os.environ.get(MODE_ENV, OFFLINE).lower()


def _seam_mode(env_name: str, base: str) -> str:
    """A seam runs at ORCHESTRATOR_MODE unless its own override env is set.

    Lets you bring up one seam at a time — e.g. GATEWAY_MODE=live to make real
    OpenRouter calls while datastore/email stay on the in-memory fakes locally.
    """
    mode = os.environ.get(env_name, base).lower()
    if mode not in (LIVE, OFFLINE):
        raise CompositionError(f"unknown {env_name}={mode!r}; expected 'offline' or 'live'")
    return mode


def default_model_map(config: GatewayConfig) -> dict[str, tuple[str, int]]:
    """Per-agent (model_id, max_tokens). Single-provider start: judgment stages get
    the frontier model, mechanical stages the smaller one (context §6)."""
    frontier = config.conversation_model
    slm = config.extraction_model
    return {
        "intake-conversation": (frontier, config.conversation_max_tokens),
        "intake-extraction": (slm, config.extraction_max_tokens),
        "stack-check": (frontier, 1500),
        "triage-recommender": (frontier, 2000),
        "cost-estimation-rom": (slm, config.extraction_max_tokens),
        "cost-estimation-deepdive": (frontier, 2500),
        "build-agent": (frontier, 4000),
        "functional-qa": (frontier, 2500),
        "security-vulnerabilities": (frontier, 2500),
        "security-governance": (frontier, 2500),
        "portfolio-pattern": (slm, 2000),
        "registry-maintenance": (slm, 2000),
    }


def build_gateway(mode: str) -> ModelGateway:
    if mode == LIVE:
        config = load_gateway_config()
        if not config.has_key:
            raise CompositionError("live mode: OPENROUTER_API_KEY is required")
        return OpenRouterGateway(config, default_model_map(config))
    return FakeModelGateway()


def build_datastore(mode: str) -> Datastore:
    if mode == LIVE:
        config = load_airtable_config()
        if not config.is_configured:
            raise CompositionError("live mode: AIRTABLE_API_KEY and AIRTABLE_BASE_ID are required")
        return AirtableDatastore(config)
    return InMemoryDatastore()


def build_emailer(mode: str) -> Emailer:
    if mode == LIVE:
        config = load_emailer_config()
        if not config.has_key or not config.from_address:
            raise CompositionError("live mode: RESEND_API_KEY and RESEND_FROM are required")
        return ResendEmailer(config)
    return InMemoryEmailer()


def build_services(mode: str | None = None, *, identity: IdentityProvider | None = None) -> Services:
    """Build the wired seams. ORCHESTRATOR_MODE sets the baseline; each seam may be
    overridden via GATEWAY_MODE / DATASTORE_MODE / EMAILER_MODE (offline|live)."""
    base = (mode or current_mode()).lower()
    if base not in (LIVE, OFFLINE):
        raise CompositionError(f"unknown {MODE_ENV}={base!r}; expected 'offline' or 'live'")
    gateway_mode = _seam_mode("GATEWAY_MODE", base)
    datastore_mode = _seam_mode("DATASTORE_MODE", base)
    emailer_mode = _seam_mode("EMAILER_MODE", base)

    datastore = build_datastore(datastore_mode)
    # stack-check reads the registry when the gateway is live; else an empty one.
    registry = default_registry_source() if gateway_mode == LIVE else InMemoryRegistry([])
    # The real SSO/identity provider is resolved at the web/session layer (deferred);
    # offline and un-injected live both use the fake, which the web layer replaces.
    return Services(
        mode=base,
        gateway=build_gateway(gateway_mode),
        datastore=datastore,
        emailer=build_emailer(emailer_mode),
        registry_source=registry,
        identity=identity or FakeIdentityProvider(),
        audit=AuditLog(datastore),
    )


def make_intake_runner(
    services: Services, *, request_id: str, max_attempts: int = DEFAULT_MAX_ATTEMPTS
) -> IntakeRunner:
    """Construct an IntakeRunner from the wired services (the conversation->record loop)."""
    return IntakeRunner(
        gateway=services.gateway,
        datastore=services.datastore,
        audit=services.audit,
        conversation_spec=load_intake_conversation_spec(),
        extraction_spec=load_intake_extraction_spec(),
        request_id=request_id,
        max_attempts=max_attempts,
    )


def make_pipeline_runner(
    services: Services,
    *,
    pipeline: Pipeline,
    state: RunState,
    request_id: str,
    director_email: str | None = None,
    **kwargs,
) -> PipelineRunner:
    """Construct a PipelineRunner from the wired services (post-intake driver)."""
    return PipelineRunner(
        pipeline=pipeline,
        state=state,
        request_id=request_id,
        gateway=services.gateway,
        datastore=services.datastore,
        emailer=services.emailer,
        audit=services.audit,
        registry_source=services.registry_source,
        director_email=director_email or ai_enabler_email(),
        **kwargs,
    )


def rehydrate_runner(services: Services, request_id: str) -> PipelineRunner:
    """Rebuild a PipelineRunner from its persisted snapshot (durable resume).

    The web layer holds no runner between calls: each gate decision rehydrates,
    resumes, and re-persists. Raises if no snapshot exists for the id.
    """
    snapshot = services.datastore.get_record(f"{request_id}:snapshot")
    if snapshot is None:
        raise CompositionError(f"no persisted snapshot for request '{request_id}'")
    return PipelineRunner.from_snapshot(
        snapshot,
        gateway=services.gateway,
        datastore=services.datastore,
        emailer=services.emailer,
        audit=services.audit,
        registry_source=services.registry_source,
    )


def pipeline_runner_after_intake(
    services: Services, outcome: IntakeOutcome, *, request_id: str, **kwargs
) -> PipelineRunner:
    """Hand intake's result to the pipeline driver — the one lifecycle seam.

    Intake leaves the pipeline at analysis with the record stored and the
    transcript persisted; this rebuilds the RunState from those and returns a
    PipelineRunner positioned to advance().
    """
    if outcome.status != "record_ready" or outcome.record is None:
        raise CompositionError(f"intake outcome is '{outcome.status}', not record_ready")
    transcript = services.datastore.get_transcript(outcome.transcript_reference or "") or ""
    state = RunState(intake_record=outcome.record, transcript=transcript)
    return make_pipeline_runner(
        services, pipeline=outcome.pipeline, state=state, request_id=request_id, **kwargs
    )
