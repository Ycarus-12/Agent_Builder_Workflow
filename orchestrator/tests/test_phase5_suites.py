"""Phase 5: stack-check + triage replay suites and their specs."""

from app.agents import (
    load_stack_check_spec,
    load_triage_spec,
    stack_check_finding_schema,
    triage_output_schema,
)
from app.evals.runner import run_stack_check_suite_replay, run_triage_suite_replay
from app.invocation import OutputMode, Tier


def test_stack_check_spec_loads():
    spec = load_stack_check_spec()
    assert spec.name == "stack-check"
    assert spec.tier is Tier.MID
    assert spec.output_mode is OutputMode.STRUCTURED
    assert spec.block_names == ("intake_record",)
    assert spec.output_schema["title"] == "StackCheckFinding"
    assert "agent: stack-check" not in spec.system_prompt


def test_triage_spec_loads():
    spec = load_triage_spec()
    assert spec.name == "triage-recommender"
    assert spec.tier is Tier.HIGH
    assert spec.block_names == ("intake_record", "transcript", "stack_check_result")
    assert spec.output_schema["title"] == "TriageOptionListAndRecommendation"


def test_stack_check_replay_all_green():
    suite = run_stack_check_suite_replay(stack_check_finding_schema())
    failed = [(c.case_id, c.failures) for c in suite.cases]
    assert suite.ok, f"stack-check replay should pass; failures: {failed}"
    ids = {c.case_id for c in suite.cases}
    assert {"S1", "S2", "S3"} <= ids
    assert {"S_neg_invented", "S_neg_recommendation", "S_neg_dropped"} <= ids


def test_triage_replay_all_green():
    suite = run_triage_suite_replay(triage_output_schema())
    failed = [(c.case_id, c.failures) for c in suite.cases]
    assert suite.ok, f"triage replay should pass; failures: {failed}"
    ids = {c.case_id for c in suite.cases}
    assert {"T1", "T3", "T6"} <= ids
    assert {"T_neg_configure_floor", "T_neg_route_mismatch", "T_neg_trace"} <= ids


def test_negatives_actually_fail_the_engine():
    # Sanity: confirm the engine truly rejects the negatives (not a fixture mislabel).
    from app.evals.loader import load_stack_check_fixtures, load_triage_fixtures
    from app.evals.stack_check_assertions import check_stack_check
    from app.evals.triage_assertions import check_triage

    sc = {f.case_id: f for f in load_stack_check_fixtures()}
    neg = sc["S_neg_invented"]
    assert not check_stack_check(neg, neg.recorded_output, stack_check_finding_schema()).passed

    tr = {f.case_id: f for f in load_triage_fixtures()}
    negt = tr["T_neg_route_mismatch"]
    assert not check_triage(negt, negt.recorded_output, triage_output_schema()).passed
