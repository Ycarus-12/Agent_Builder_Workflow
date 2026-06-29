import pytest

from app.enums import DataSensitivity, Outcome, Weight
from app.state_machine import (
    AnalysisStep,
    Gate1aDecision,
    IllegalTransition,
    Pipeline,
    Stage,
)


def _to_gate_1a(p: Pipeline, outcome: Outcome = Outcome.BUILD) -> None:
    p.requestor_signoff()
    p.extraction_complete()
    assert p.stage is Stage.ANALYSIS and p.analysis_step is AnalysisStep.STACK_CHECK
    p.advance_analysis()  # -> triage
    assert p.analysis_step is AnalysisStep.TRIAGE
    p.set_triage_recommendation(outcome)
    p.advance_analysis()  # -> cost_rom
    assert p.analysis_step is AnalysisStep.COST_ROM
    p.advance_analysis()  # -> gate_1a
    assert p.stage is Stage.GATE_1A


def test_happy_path_deep_dive_to_deploy():
    p = Pipeline(weight=Weight.LIGHT, data_sensitivity=DataSensitivity.INTERNAL)
    _to_gate_1a(p)
    assert p.is_stop_point
    p.apply_gate_1a(Gate1aDecision.DEEP_DIVE, selected_options=("opt-1", "opt-2"))
    assert p.stage is Stage.COST_DEEPDIVE
    assert p.selected_options == ("opt-1", "opt-2")
    p.deepdive_complete()
    p.apply_gate_1b(approved=True)
    assert p.stage is Stage.BUILD
    p.build_complete()
    p.apply_qa(passed=True)
    assert p.stage is Stage.SECURITY_REVIEW
    p.apply_security(passed=True)  # light+internal: no R&D sign-off needed
    assert p.stage is Stage.GATE_2
    p.apply_gate_2(accepted=True)
    assert p.stage is Stage.DEPLOY_AND_REGISTER
    assert p.is_terminal


def test_accept_route_elsewhere_terminates():
    p = Pipeline()
    _to_gate_1a(p, outcome=Outcome.ROUTE_ELSEWHERE)
    p.apply_gate_1a(Gate1aDecision.ACCEPT)
    assert p.stage is Stage.TERMINATED
    assert p.is_terminal


def test_accept_dont_build_terminates():
    p = Pipeline()
    _to_gate_1a(p, outcome=Outcome.DONT_BUILD)
    p.apply_gate_1a(Gate1aDecision.ACCEPT)
    assert p.stage is Stage.TERMINATED


def test_accept_configure_proceeds_to_spend_gate():
    p = Pipeline()
    _to_gate_1a(p, outcome=Outcome.CONFIGURE)
    p.apply_gate_1a(Gate1aDecision.ACCEPT)
    assert p.stage is Stage.GATE_1B


def test_reject_re_enters_at_triage_not_stack_check():
    p = Pipeline()
    _to_gate_1a(p)
    p.apply_gate_1a(Gate1aDecision.REJECT)
    assert p.stage is Stage.ANALYSIS
    assert p.analysis_step is AnalysisStep.TRIAGE
    assert p.re_triage is True


def test_deep_dive_requires_a_selection():
    p = Pipeline()
    _to_gate_1a(p)
    with pytest.raises(IllegalTransition, match="at least one selected option"):
        p.apply_gate_1a(Gate1aDecision.DEEP_DIVE, selected_options=())


def test_qa_failure_loops_back_to_build():
    p = Pipeline()
    _to_gate_1a(p)
    p.apply_gate_1a(Gate1aDecision.DEEP_DIVE, selected_options=("opt-1",))
    p.deepdive_complete()
    p.apply_gate_1b(approved=True)
    p.build_complete()
    p.apply_qa(passed=False)
    assert p.stage is Stage.BUILD


def test_gate_1b_rejection_terminates():
    p = Pipeline()
    _to_gate_1a(p)
    p.apply_gate_1a(Gate1aDecision.DEEP_DIVE, selected_options=("opt-1",))
    p.deepdive_complete()
    p.apply_gate_1b(approved=False)
    assert p.stage is Stage.TERMINATED


def test_heavy_work_requires_rnd_signoff_to_clear_security():
    p = Pipeline(weight=Weight.HEAVY, data_sensitivity=DataSensitivity.INTERNAL)
    _to_gate_1a(p)
    p.apply_gate_1a(Gate1aDecision.DEEP_DIVE, selected_options=("opt-1",))
    p.deepdive_complete()
    p.apply_gate_1b(approved=True)
    p.build_complete()
    p.apply_qa(passed=True)
    assert p.rnd_signoff_required() is True
    with pytest.raises(IllegalTransition, match="R&D security sign-off"):
        p.apply_security(passed=True, rnd_signed_off=False)
    p.apply_security(passed=True, rnd_signed_off=True)
    assert p.stage is Stage.GATE_2


def test_unspecified_sensitivity_forces_rnd_even_when_light():
    p = Pipeline(weight=Weight.LIGHT, data_sensitivity=DataSensitivity.UNSPECIFIED)
    assert p.rnd_signoff_required() is True


def test_security_failure_loops_back_to_build():
    p = Pipeline(data_sensitivity=DataSensitivity.INTERNAL)
    _to_gate_1a(p)
    p.apply_gate_1a(Gate1aDecision.DEEP_DIVE, selected_options=("opt-1",))
    p.deepdive_complete()
    p.apply_gate_1b(approved=True)
    p.build_complete()
    p.apply_qa(passed=True)
    p.apply_security(passed=False)
    assert p.stage is Stage.BUILD


def test_gate_2_rejection_returns_to_build():
    p = Pipeline(data_sensitivity=DataSensitivity.INTERNAL)
    _to_gate_1a(p)
    p.apply_gate_1a(Gate1aDecision.DEEP_DIVE, selected_options=("opt-1",))
    p.deepdive_complete()
    p.apply_gate_1b(approved=True)
    p.build_complete()
    p.apply_qa(passed=True)
    p.apply_security(passed=True)
    p.apply_gate_2(accepted=False)
    assert p.stage is Stage.BUILD


def test_illegal_transition_from_wrong_stage():
    p = Pipeline()
    with pytest.raises(IllegalTransition):
        p.apply_gate_1b(approved=True)  # not at gate_1b


def test_intake_abandonment():
    p = Pipeline()
    p.abandon_intake()
    assert p.stage is Stage.INTAKE_ABANDONED
    assert p.is_terminal
