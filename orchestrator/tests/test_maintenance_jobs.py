"""Background jobs: registry-maintenance and portfolio-pattern run off-pipeline,
through the composition root, with validate-and-retry + audit + persistence."""

import json
from pathlib import Path

import yaml

from app.composition import build_services
from app.maintenance import run_portfolio_pattern, run_registry_maintenance

_FIX = Path(__file__).resolve().parents[1] / "evals" / "fixtures"


def _ro(rel: str) -> str:
    out = yaml.safe_load((_FIX / rel).read_text(encoding="utf-8"))["recorded_output"]
    return out if isinstance(out, str) else json.dumps(out)


def test_registry_maintenance_runs_and_persists():
    svc = build_services("offline")
    svc.gateway.script("registry-maintenance", [_ro("registry_maintenance/C1_stamp.yaml")])

    changeset = run_registry_maintenance(
        svc,
        run_context={"run_date": "2026-06-30", "trigger": "scheduled"},
        drift_report={"drifts": []},
        affected_records=[],
    )
    assert isinstance(changeset, dict)
    job_id = "registry-maintenance:2026-06-30"
    assert svc.datastore.get_record(job_id) == changeset
    audited = [e for e in svc.datastore.events
               if e["event"] == "agent_call" and e["agent"] == "registry-maintenance"]
    assert audited and audited[0]["stage"] == "background_job"


def test_portfolio_pattern_runs_and_persists():
    svc = build_services("offline")
    svc.gateway.script("portfolio-pattern", [_ro("portfolio/P1_uncovered_build.yaml")])

    digest = run_portfolio_pattern(svc, clusters=[], pseudo_agent_usage=[])
    assert isinstance(digest, dict)
    assert svc.datastore.get_record("portfolio-pattern:adhoc") == digest


def test_jobs_do_not_touch_request_pipeline_state():
    # A background job uses its own job id namespace; it never collides with a
    # request id or its ":state" key.
    svc = build_services("offline")
    svc.gateway.script("portfolio-pattern", [_ro("portfolio/P1_uncovered_build.yaml")])
    run_portfolio_pattern(svc, clusters=[], pseudo_agent_usage=[], job_id="portfolio:req-1")
    assert svc.datastore.get_record("req-1") is None
    assert svc.datastore.get_record("req-1:state") is None
