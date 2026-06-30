"""Background jobs — the two out-of-pipeline periodic agents (Architecture §10).

registry-maintenance and portfolio-pattern run OUTSIDE the request pipeline: the
first reconciles the capability registry against drift on a schedule/trigger (no
request state); the second surfaces recurring-theme recommendations to the
Director. Neither belongs in the PipelineRunner. They share the same discipline as
every agent call — validate-and-retry on the structured output, and an audited
call logging prompt version + commit hash — so this driver gives them a home
without bending the request spine around them.
"""

from __future__ import annotations

import json
from typing import Any

from .agents import load_portfolio_spec, load_registry_maintenance_spec
from .composition import Services
from .enums import DataSensitivity
from .invocation import AgentSpec, InputEnvelope
from .retry_loop import DEFAULT_MAX_ATTEMPTS, run_structured


def run_registry_maintenance(
    services: Services,
    *,
    run_context: dict[str, Any],
    drift_report: dict[str, Any],
    affected_records: list[dict[str, Any]],
    job_id: str | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> dict:
    """Run the registry-maintenance agent; return the validated registry changeset."""
    spec = load_registry_maintenance_spec()
    blocks = {
        "run_context": json.dumps(run_context),
        "drift_report": json.dumps(drift_report),
        "affected_records": json.dumps(affected_records),
    }
    job_id = job_id or f"registry-maintenance:{run_context.get('run_date', 'adhoc')}"
    return _run_job(services, spec, blocks, job_id, max_attempts)


def run_portfolio_pattern(
    services: Services,
    *,
    clusters: list[dict[str, Any]],
    pseudo_agent_usage: dict[str, Any] | list[dict[str, Any]],
    job_id: str | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> dict:
    """Run the portfolio-pattern agent; return the validated portfolio digest."""
    spec = load_portfolio_spec()
    blocks = {
        "clusters": json.dumps(clusters),
        "pseudo_agent_usage": json.dumps(pseudo_agent_usage),
    }
    job_id = job_id or "portfolio-pattern:adhoc"
    return _run_job(services, spec, blocks, job_id, max_attempts)


def _run_job(services: Services, spec: AgentSpec, blocks: dict[str, str], job_id: str, max_attempts: int) -> dict:
    envelope = InputEnvelope(spec=spec, blocks=blocks)
    record = run_structured(
        services.gateway, envelope, max_attempts=max_attempts,
        log_event=lambda e: services.audit.raw(job_id, e),
    )
    # Registry/portfolio jobs carry no request data; nothing to redact (NONE).
    services.audit.agent_call(
        request_id=job_id, stage="background_job", agent_name=spec.name,
        prompt_version=spec.version, commit_hash=spec.commit_hash,
        input_rendered=envelope.render(), output=record,
        sensitivity=DataSensitivity.NONE, validation_result="valid", retry_count=0,
    )
    services.datastore.store_record(job_id, record)
    return record
