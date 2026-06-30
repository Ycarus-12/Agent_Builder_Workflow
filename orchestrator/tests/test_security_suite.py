from app.agents import (
    load_security_gov_spec,
    load_security_vuln_spec,
    security_gov_schema,
    security_vuln_schema,
)
from app.evals.loader import load_security_gov_fixtures, load_security_vuln_fixtures
from app.evals.runner import run_security_suite_replay
from app.evals.security_assertions import check_security
from app.invocation import OutputMode, Tier


def test_security_specs_load():
    v = load_security_vuln_spec()
    g = load_security_gov_spec()
    assert v.name == "security-vulnerabilities" and v.tier is Tier.HIGH
    assert g.name == "security-governance"
    assert v.output_mode is OutputMode.STRUCTURED
    assert v.output_schema["title"] == "SecurityVulnerabilitiesOutput"
    assert g.output_schema["title"] == "SecurityGovernanceOutput"
    assert "governance_standard" in g.block_names


def test_security_replay_all_green():
    suite = run_security_suite_replay(security_vuln_schema(), security_gov_schema())
    failed = [(c.case_id, c.failures) for c in suite.cases]
    assert suite.ok, f"security replay should pass; failures: {failed}"
    ids = {c.case_id for c in suite.cases}
    assert {"SV1", "SV2", "SG1", "SG2"} <= ids
    assert {"SV_neg_nonsequential", "SV_neg_verdict", "SG_neg_sensitivity", "SG_neg_prefix"} <= ids


def test_security_negatives_truly_fail_engine():
    vuln = {f.case_id: f for f in load_security_vuln_fixtures()}
    gov = {f.case_id: f for f in load_security_gov_fixtures()}
    assert not check_security(vuln["SV_neg_nonsequential"], vuln["SV_neg_nonsequential"].recorded_output, security_vuln_schema()).passed
    assert not check_security(gov["SG_neg_sensitivity"], gov["SG_neg_sensitivity"].recorded_output, security_gov_schema()).passed
