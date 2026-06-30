"""Tests for the build needs_input loop and the two-security reconciliation."""

import pytest

from app.enums import DataSensitivity, Weight
from app.security_review import reconcile_security
from app.state_machine import IllegalTransition, Pipeline, Stage


def _to_build(p: Pipeline) -> None:
    p.requestor_signoff()
    p.extraction_complete()
    p.advance_analysis()  # triage
    p.advance_analysis()  # cost_rom
    p.advance_analysis()  # gate_1a
    from app.state_machine import Gate1aDecision
    p.apply_gate_1a(Gate1aDecision.DEEP_DIVE, selected_options=("opt-1",))
    p.deepdive_complete()
    p.apply_gate_1b(approved=True)
    assert p.stage is Stage.BUILD


# -- build needs_input loop --------------------------------------------------
def test_build_needs_input_pauses_then_resumes():
    p = Pipeline(data_sensitivity=DataSensitivity.INTERNAL)
    _to_build(p)
    p.build_needs_input(("q1", "q2"))
    assert p.is_awaiting_build_input
    assert p.stage is Stage.BUILD
    with pytest.raises(IllegalTransition, match="awaiting Director input"):
        p.build_complete()
    p.build_provide_responses()
    assert not p.is_awaiting_build_input
    p.build_complete()
    assert p.stage is Stage.QA_FUNCTIONAL


def test_build_needs_input_requires_questions():
    p = Pipeline()
    _to_build(p)
    with pytest.raises(IllegalTransition, match="at least one question"):
        p.build_needs_input(())


def test_resume_without_pending_questions_is_illegal():
    p = Pipeline()
    _to_build(p)
    with pytest.raises(IllegalTransition, match="no pending build questions"):
        p.build_provide_responses()


# -- security reconciliation -------------------------------------------------
def _crit():
    return [{"severity": "Critical"}]


def test_critical_blocks_and_is_non_bypassable():
    out = reconcile_security(_crit(), [], weight=Weight.LIGHT, data_sensitivity=DataSensitivity.INTERNAL)
    assert out.blocked and out.critical
    p = Pipeline(data_sensitivity=DataSensitivity.INTERNAL)
    _to_build(p)
    p.build_complete()
    p.apply_qa(passed=True)
    # even with a Director "clear", a Critical sends it back to build
    p.apply_reconciled_security(out, rnd_signed_off=True, director_cleared=True)
    assert p.stage is Stage.BUILD


def test_high_finding_routes_to_director():
    out = reconcile_security([{"severity": "High"}], [], weight=Weight.LIGHT, data_sensitivity=DataSensitivity.INTERNAL)
    assert out.to_director and not out.blocked
    p = Pipeline(data_sensitivity=DataSensitivity.INTERNAL)
    _to_build(p)
    p.build_complete()
    p.apply_qa(passed=True)
    with pytest.raises(IllegalTransition, match="Director adjudication"):
        p.apply_reconciled_security(out)
    p.apply_reconciled_security(out, director_cleared=True)
    assert p.stage is Stage.GATE_2


def test_disagreement_flagged():
    # vuln raises High, governance silent -> material disagreement
    out = reconcile_security([{"severity": "High"}], [], weight=Weight.LIGHT, data_sensitivity=DataSensitivity.NONE)
    assert out.disagreement and out.to_director


def test_clean_review_clears_to_gate_2():
    out = reconcile_security([{"severity": "Low"}], [{"severity": "Informational"}],
                             weight=Weight.LIGHT, data_sensitivity=DataSensitivity.INTERNAL)
    assert out.clears_to_gate_2
    p = Pipeline(data_sensitivity=DataSensitivity.INTERNAL)
    _to_build(p)
    p.build_complete()
    p.apply_qa(passed=True)
    p.apply_reconciled_security(out)
    assert p.stage is Stage.GATE_2


def test_heavy_work_still_needs_rnd_signoff_even_when_clean():
    out = reconcile_security([], [], weight=Weight.HEAVY, data_sensitivity=DataSensitivity.INTERNAL)
    assert out.rnd_signoff_required and out.clears_to_gate_2
    p = Pipeline(weight=Weight.HEAVY, data_sensitivity=DataSensitivity.INTERNAL)
    _to_build(p)
    p.build_complete()
    p.apply_qa(passed=True)
    with pytest.raises(IllegalTransition, match="R&D security sign-off"):
        p.apply_reconciled_security(out)
    p.apply_reconciled_security(out, rnd_signed_off=True)
    assert p.stage is Stage.GATE_2
