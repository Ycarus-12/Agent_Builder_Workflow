"""The pipeline state machine (orchestrator-contract §2).

Deterministic transitions except at the explicit human gates. The orchestrator
holds no judgment: it sequences stages, enforces the stop list, and routes per the
Director's gate decisions. Triage recommends; the Director decides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .enums import TERMINAL_OUTCOMES, Outcome, Weight
from .sensitivity import DataSensitivity, forces_rnd_signoff


class Stage(str, Enum):
    INTAKE_OPEN = "intake_open"
    INTAKE_EXTRACT = "intake_extract"
    ANALYSIS = "analysis"
    GATE_1A = "gate_1a"
    COST_DEEPDIVE = "cost_deepdive"
    GATE_1B = "gate_1b"
    BUILD = "build"
    QA_FUNCTIONAL = "qa_functional"
    SECURITY_REVIEW = "security_review"
    GATE_2 = "gate_2"
    DEPLOY_AND_REGISTER = "deploy_and_register"  # terminal (success)
    TERMINATED = "terminated"                    # terminal (route_elsewhere/dont_build/declined)
    INTAKE_ABANDONED = "intake_abandoned"        # terminal (session timeout, §4.5)


class AnalysisStep(str, Enum):
    """The analysis sub-pipeline runs these in order (§2 state 3)."""

    STACK_CHECK = "stack_check"
    TRIAGE = "triage"
    COST_ROM = "cost_rom"


_ANALYSIS_ORDER = (AnalysisStep.STACK_CHECK, AnalysisStep.TRIAGE, AnalysisStep.COST_ROM)

# The only states that can halt a request awaiting a human (the stop list, §2).
# Requestor sign-off (close of intake_open) and the R&D security sign-off (inside
# security_review) are the two embedded stops; the three Director gates are here.
DIRECTOR_GATES = frozenset({Stage.GATE_1A, Stage.GATE_1B, Stage.GATE_2})
TERMINAL_STAGES = frozenset(
    {Stage.DEPLOY_AND_REGISTER, Stage.TERMINATED, Stage.INTAKE_ABANDONED}
)


class IllegalTransition(RuntimeError):
    """Raised when a transition is attempted from the wrong stage."""


class Gate1aDecision(str, Enum):
    DEEP_DIVE = "deep_dive"   # pick 1+ options for deep-dive
    ACCEPT = "accept"         # accept the triage recommendation directly
    REJECT = "reject"         # send back for re-triage with notes


@dataclass
class Pipeline:
    """One request's position in the state machine."""

    stage: Stage = Stage.INTAKE_OPEN
    analysis_step: AnalysisStep | None = None
    re_triage: bool = False
    triage_outcome: Outcome | None = None
    selected_options: tuple[str, ...] = ()
    weight: Weight = Weight.LIGHT
    data_sensitivity: DataSensitivity = DataSensitivity.UNSPECIFIED
    # Build clarification loop (orchestrator-contract §3, build-agent v1.0.0 changelog):
    # build may return needs_input; the request pauses in BUILD for the Director's answers.
    awaiting_build_input: bool = False
    pending_build_questions: tuple[str, ...] = ()
    history: list[str] = field(default_factory=list)

    # -- helpers ----------------------------------------------------------
    def _go(self, stage: Stage, *, step: AnalysisStep | None = None) -> None:
        self.stage = stage
        self.analysis_step = step
        self.history.append(stage.value if step is None else f"{stage.value}:{step.value}")

    def _require(self, *stages: Stage) -> None:
        if self.stage not in stages:
            raise IllegalTransition(
                f"expected one of {[s.value for s in stages]}, in {self.stage.value}"
            )

    @property
    def is_stop_point(self) -> bool:
        return self.stage in DIRECTOR_GATES

    @property
    def is_terminal(self) -> bool:
        return self.stage in TERMINAL_STAGES

    # -- intake -----------------------------------------------------------
    def requestor_signoff(self) -> None:
        """Close of intake_open: the requestor confirms their own request (§2 stop)."""
        self._require(Stage.INTAKE_OPEN)
        self._go(Stage.INTAKE_EXTRACT)

    def abandon_intake(self) -> None:
        """Session timed out before the marker fired (§4.5)."""
        self._require(Stage.INTAKE_OPEN)
        self._go(Stage.INTAKE_ABANDONED)

    def extraction_complete(self) -> None:
        self._require(Stage.INTAKE_EXTRACT)
        self._go(Stage.ANALYSIS, step=AnalysisStep.STACK_CHECK)

    # -- analysis sub-pipeline -------------------------------------------
    def advance_analysis(self) -> None:
        """Step stack_check -> triage -> cost_rom; then halt at gate_1a."""
        self._require(Stage.ANALYSIS)
        assert self.analysis_step is not None
        idx = _ANALYSIS_ORDER.index(self.analysis_step)
        if idx + 1 < len(_ANALYSIS_ORDER):
            self._go(Stage.ANALYSIS, step=_ANALYSIS_ORDER[idx + 1])
        else:
            self._go(Stage.GATE_1A)

    def set_triage_recommendation(self, outcome: Outcome) -> None:
        """Record triage's recommendation (used to route an ACCEPT at gate_1a)."""
        if self.stage is not Stage.ANALYSIS or self.analysis_step is not AnalysisStep.TRIAGE:
            raise IllegalTransition("triage recommendation only valid at analysis:triage")
        self.triage_outcome = outcome

    # -- gate 1a ----------------------------------------------------------
    def apply_gate_1a(
        self,
        decision: Gate1aDecision,
        *,
        selected_options: tuple[str, ...] = (),
    ) -> None:
        self._require(Stage.GATE_1A)
        if decision is Gate1aDecision.DEEP_DIVE:
            if not selected_options:
                raise IllegalTransition("DEEP_DIVE requires at least one selected option")
            self.selected_options = selected_options
            self._go(Stage.COST_DEEPDIVE)
        elif decision is Gate1aDecision.ACCEPT:
            if self.triage_outcome in TERMINAL_OUTCOMES:
                # route_elsewhere / dont_build: record, notify/hand-off, terminate.
                self._go(Stage.TERMINATED)
            else:
                # proceeds-as-configured: straight to the spend gate.
                self._go(Stage.GATE_1B)
        elif decision is Gate1aDecision.REJECT:
            # Re-enter analysis at triage (stack-check finding still valid, §2).
            self.re_triage = True
            self._go(Stage.ANALYSIS, step=AnalysisStep.TRIAGE)
        else:  # pragma: no cover - exhaustive
            raise IllegalTransition(f"unknown gate_1a decision {decision}")

    # -- deep-dive + spend gate ------------------------------------------
    def deepdive_complete(self) -> None:
        self._require(Stage.COST_DEEPDIVE)
        self._go(Stage.GATE_1B)

    def apply_gate_1b(self, *, approved: bool) -> None:
        self._require(Stage.GATE_1B)
        self._go(Stage.BUILD if approved else Stage.TERMINATED)

    # -- build / QA / security / accept ----------------------------------
    def build_needs_input(self, question_ids: tuple[str, ...]) -> None:
        """Build returned build_status=needs_input: pause in BUILD for the Director.

        Routes the agent's questions to the Director; the request does not advance.
        On answers, the orchestrator re-invokes build via build_provide_responses().
        """
        self._require(Stage.BUILD)
        if not question_ids:
            raise IllegalTransition("needs_input requires at least one question")
        self.awaiting_build_input = True
        self.pending_build_questions = tuple(question_ids)
        self.history.append(f"{Stage.BUILD.value}:needs_input")

    def build_provide_responses(self) -> None:
        """Director answered: clear the pending questions and re-invoke build."""
        self._require(Stage.BUILD)
        if not self.awaiting_build_input:
            raise IllegalTransition("no pending build questions to answer")
        self.awaiting_build_input = False
        self.pending_build_questions = ()
        self.history.append(f"{Stage.BUILD.value}:resume")

    @property
    def is_awaiting_build_input(self) -> bool:
        return self.stage is Stage.BUILD and self.awaiting_build_input

    def build_complete(self) -> None:
        self._require(Stage.BUILD)
        if self.awaiting_build_input:
            raise IllegalTransition("build cannot complete while awaiting Director input")
        self._go(Stage.QA_FUNCTIONAL)

    def apply_qa(self, *, passed: bool) -> None:
        self._require(Stage.QA_FUNCTIONAL)
        # Functional QA failures loop back to build (§2 state 8).
        self._go(Stage.SECURITY_REVIEW if passed else Stage.BUILD)

    def rnd_signoff_required(self) -> bool:
        """Heavy or sensitive work also takes the R&D security sign-off (§2, §6)."""
        return forces_rnd_signoff(self.data_sensitivity, self.weight)

    def apply_security(self, *, passed: bool, rnd_signed_off: bool = False) -> None:
        """Two security agents + scanners; non-bypassable, including by the Director.

        - Critical findings (not passed) loop back to build for remediation.
        - If the R&D sign-off is required, it must be present to clear the stage
          (the embedded stop point); otherwise the request halts in
          security_review awaiting that sign-off.
        """
        self._require(Stage.SECURITY_REVIEW)
        if not passed:
            self._go(Stage.BUILD)
            return
        if self.rnd_signoff_required() and not rnd_signed_off:
            # Stays in security_review: the R&D sign-off is an embedded stop.
            raise IllegalTransition(
                "security_review requires the R&D security sign-off (heavy/sensitive)"
            )
        self._go(Stage.GATE_2)

    def apply_reconciled_security(
        self, outcome, *, rnd_signed_off: bool = False, director_cleared: bool = False
    ) -> None:
        """Apply the orchestrator-reconciled outcome of the two blind security agents.

        Precedence (security is non-bypassable, including by the Director):
        1. A Critical finding blocks unconditionally -> back to build for remediation.
        2. A High finding / material disagreement awaits Director adjudication.
        3. Heavy or sensitive work awaits the R&D security sign-off.
        Only when none of these hold does the request clear to gate_2.
        """
        self._require(Stage.SECURITY_REVIEW)
        if outcome.blocked:
            self._go(Stage.BUILD)
            return
        if outcome.to_director and not director_cleared:
            raise IllegalTransition("security_review awaits Director adjudication (High/disagreement)")
        if outcome.rnd_signoff_required and not rnd_signed_off:
            raise IllegalTransition("security_review requires the R&D security sign-off (heavy/sensitive)")
        self._go(Stage.GATE_2)

    def apply_gate_2(self, *, accepted: bool) -> None:
        self._require(Stage.GATE_2)
        # Acceptance deploys; rejection returns the tool to build for rework.
        self._go(Stage.DEPLOY_AND_REGISTER if accepted else Stage.BUILD)
