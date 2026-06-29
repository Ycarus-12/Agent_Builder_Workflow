"""Tests for the eval harness: the deterministic engine + the fixtures.

The fixtures are self-validating — positives must pass and negatives must be
caught — which is what makes the every-commit replay gate meaningful (§7.3).
"""

from app.agents import intake_record_schema
from app.evals.assertions import check_conversation, compute_terminal_state
from app.evals.loader import load_conversation_fixtures, load_extraction_fixtures
from app.evals.runner import run_intake_suite_replay


def test_replay_suite_all_green():
    suite = run_intake_suite_replay(intake_record_schema())
    failed = [(c.case_id, c.failures) for c in suite.cases]
    assert suite.ok, f"replay suite should pass; failures: {failed}"
    # Sanity: the suite actually loaded a meaningful number of cases.
    assert len(suite.cases) >= 15


def test_every_fixture_present():
    ex = {f.case_id for f in load_extraction_fixtures()}
    conv = {f.case_id for f in load_conversation_fixtures()}
    assert {"E1", "E2", "E3", "E4"} <= ex
    assert {"C1", "C2", "C3", "C4", "C5", "C6"} <= conv


def test_negative_extraction_fixtures_are_caught():
    # Negative fixtures (expect_result: fail) must be rejected by the engine; the
    # runner reports them as passed cases only because they correctly failed.
    suite = run_intake_suite_replay(intake_record_schema())
    by_id = {c.case_id: c for c in suite.cases}
    for neg in ("E_neg_prose", "E_neg_sensitivity_none", "E_neg_autofill"):
        assert by_id[neg].passed, f"{neg} should be a (correctly-caught) pass"


def test_conversation_hard_fail_detection_directly():
    # marker fired but no prior confirmation
    state = compute_terminal_state(
        [{"role": "requestor", "content": "maybe that's it"}],
        ["All set.\n\n[[INTAKE_SIGNOFF_CONFIRMED]]"],
    )
    assert state == "hard_fail_marker_no_confirmation"

    # scope/route violation
    assert compute_terminal_state(
        [{"role": "requestor", "content": "vpn"}], ["That's a job for IT."]
    ) == "hard_fail_scope_route"

    # cost/timeline promise
    assert compute_terminal_state(
        [{"role": "requestor", "content": "x"}], ["we can build that by next week"]
    ) == "hard_fail_cost_timeline"

    # clean confirmed sign-off
    assert compute_terminal_state(
        [{"role": "requestor", "content": "yes, that's correct"}],
        ["Recorded.\n\n[[INTAKE_SIGNOFF_CONFIRMED]]"],
    ) == "marker_fired"


def test_multiple_questions_is_soft_signal_not_failure():
    fx = type("F", (), {
        "case_id": "Cq", "turns": [{"role": "requestor", "content": "hi"}],
        "expected_terminal_state": "conversation_in_progress",
    })()
    result = check_conversation(fx, ["What, why, and how? Also when? And who?"])
    assert result.passed  # still passes...
    assert result.soft_signals  # ...but the soft signal is reported
