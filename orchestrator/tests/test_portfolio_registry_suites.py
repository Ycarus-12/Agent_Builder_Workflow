from app.agents import (
    load_portfolio_spec,
    load_registry_maintenance_spec,
    portfolio_digest_schema,
    registry_changeset_schema,
)
from app.evals.loader import load_portfolio_fixtures, load_registry_maintenance_fixtures
from app.evals.portfolio_assertions import check_portfolio
from app.evals.registry_maintenance_assertions import check_registry_maintenance
from app.evals.runner import (
    run_portfolio_suite_replay,
    run_registry_maintenance_suite_replay,
)
from app.invocation import OutputMode, Tier


def test_specs_load():
    p = load_portfolio_spec()
    r = load_registry_maintenance_spec()
    assert p.name == "portfolio-pattern" and p.tier is Tier.MID
    assert r.name == "registry-maintenance"
    assert p.output_mode is OutputMode.STRUCTURED
    assert p.output_schema["title"] == "PortfolioDigest"
    assert r.output_schema["title"] == "RegistryChangeset"
    assert p.block_names == ("clusters", "pseudo_agent_usage")
    assert r.block_names == ("run_context", "drift_report", "affected_records")


def test_portfolio_replay_all_green():
    suite = run_portfolio_suite_replay(portfolio_digest_schema())
    failed = [(c.case_id, c.failures) for c in suite.cases]
    assert suite.ok, f"portfolio replay should pass; failures: {failed}"
    ids = {c.case_id for c in suite.cases}
    assert {"P1", "P2", "P4", "P5"} <= ids
    assert {"P_neg_tier", "P_neg_coverage_coupling", "P_neg_provenance"} <= ids


def test_registry_maintenance_replay_all_green():
    suite = run_registry_maintenance_suite_replay(registry_changeset_schema())
    failed = [(c.case_id, c.failures) for c in suite.cases]
    assert suite.ok, f"registry-maintenance replay should pass; failures: {failed}"
    ids = {c.case_id for c in suite.cases}
    assert {"C1", "C2"} <= ids
    assert {"C_neg_class", "C_neg_produce", "C_neg_stamp_date"} <= ids


def test_negatives_truly_fail_engine():
    p = {f.case_id: f for f in load_portfolio_fixtures()}
    r = {f.case_id: f for f in load_registry_maintenance_fixtures()}
    assert not check_portfolio(p["P_neg_tier"], p["P_neg_tier"].recorded_output, portfolio_digest_schema()).passed
    assert not check_registry_maintenance(
        r["C_neg_class"], r["C_neg_class"].recorded_output, registry_changeset_schema()
    ).passed
