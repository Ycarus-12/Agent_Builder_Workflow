"""Judge-model rubric harness (orchestrator-contract §7.2, §7.3).

The quality layer on top of the deterministic gates: a grader model scores an
agent's output 1-5 across named dimensions. Per §7.2 it runs three times per case
and the MEDIAN is scored (to damp judge variance), and is out of scope for
every-commit CI — it runs weekly / on prompt-touch and needs model access.

This module is the deterministic scaffold: rubric definitions, median aggregation,
and the §7.3 merge rule. The judge call itself is behind the JudgeGateway seam
(FakeJudge for tests; an OpenRouter-backed judge when a key is present).
"""

from __future__ import annotations

import statistics
from abc import ABC, abstractmethod
from dataclasses import dataclass

PASS_BAR = 3          # a dimension passes at median >= 3 (§7.2)
MAX_BASELINE_DROP = 1  # a drop > 1 below baseline on any dimension blocks merge (§7.3)


@dataclass(frozen=True)
class RubricDimension:
    name: str
    description: str


# Dimension sets vendored from each judge-bearing eval suite's rubric table.
RUBRICS: dict[str, tuple[RubricDimension, ...]] = {
    "intake-conversation": (
        RubricDimension("problem_vs_tool", "Captures the problem behind the named tool."),
        RubricDimension("reframing_solution_talk", "Steers solution-talk back to the problem."),
        RubricDimension("workaround_depth", "Captures the current workaround concretely."),
        RubricDimension("routing_critical_fields", "Elicits data sensitivity and customer-facing."),
        RubricDimension("acceptance_criteria", "Drafts concrete, testable acceptance criteria."),
        RubricDimension("signoff_discipline", "Marker only after explicit confirmation."),
        RubricDimension("stays_in_lane", "Captures only; never decides, costs, or routes."),
    ),
    "cost-estimation-deepdive": (
        RubricDimension("phase_decomposition_quality", "Phases fit the route/avenue; specific names."),
        RubricDimension("effort_range_honesty", "low/expected/high reflect real uncertainty."),
        RubricDimension("pricing_accuracy", "Cited figures match current sources."),
        RubricDimension("maintenance_estimation", "Monthly-hours figure has a specific rationale."),
        RubricDimension("assumption_explicitness", "Every material assumption is stated."),
        RubricDimension("risk_identification", "Risks are option-specific, not generic."),
        RubricDimension("recommendation_calibration", "Recommendation calibrated to N."),
        RubricDimension("rom_band_alignment", "Divergence from the ROM band is surfaced."),
        RubricDimension("output_cleanliness", "Schema-valid, complete citations, no invented prices."),
    ),
    "build-agent": (
        RubricDimension("correct_avenue_handling", "Builds by the assigned avenue's method."),
        RubricDimension("ac_traceability", "Every criterion mapped to a location/method."),
        RubricDimension("no_self_grade", "Reports build facts only; no verdict."),
        RubricDimension("asks_vs_invents", "Returns needs_input rather than guessing."),
    ),
    "functional-qa": (
        RubricDimension("independent_verification", "Verdict rests on QA's own observation."),
        RubricDimension("verdict_correctness", "Per-criterion and overall verdicts are right."),
        RubricDimension("evidence_quality", "Each criterion has a concrete method + evidence."),
        RubricDimension("functional_only_discipline", "Stays in functional scope; no security verdict."),
        RubricDimension("no_acceptance_overreach", "Functional verdict only; defers acceptance."),
        RubricDimension("ambiguity_as_finding", "Reports ambiguity; never guesses."),
    ),
    "portfolio-pattern": (
        RubricDimension("correct_tier", "Tier matches the count mapping; ordered by urgency."),
        RubricDimension("noise_floor_suppression", "Sub-threshold clusters counted, not itemized."),
        RubricDimension("signal_type_correctness", "build/enablement/route-recurrence is right."),
        RubricDimension("coverage_judgment", "Coverage cited only on genuine resolution."),
        RubricDimension("enablement_provenance", "registry_coverage traces to a candidate."),
        RubricDimension("graduation_grounded", "Graduation rests on usage, not cluster size."),
    ),
}


@dataclass(frozen=True)
class DimensionScore:
    dimension: str
    score: int          # 1-5
    rationale: str


class JudgeGateway(ABC):
    """One grader run: score every dimension for a subject. Returns 1-5 per dimension."""

    @abstractmethod
    def score(self, agent_name: str, dimensions: tuple[RubricDimension, ...], subject: str) -> list[DimensionScore]: ...


@dataclass
class RubricResult:
    agent_name: str
    medians: dict[str, float]
    runs: int

    @property
    def passed(self) -> bool:
        return all(m >= PASS_BAR for m in self.medians.values())

    def regressed_vs(self, baseline: dict[str, float]) -> list[str]:
        """Dimensions that dropped more than MAX_BASELINE_DROP below baseline (§7.3)."""
        out = []
        for dim, median in self.medians.items():
            base = baseline.get(dim)
            if base is not None and (base - median) > MAX_BASELINE_DROP:
                out.append(dim)
        return out


def grade(judge: JudgeGateway, agent_name: str, subject: str, *, runs: int = 3) -> RubricResult:
    """Run the judge `runs` times and take the per-dimension median (§7.2)."""
    dims = RUBRICS.get(agent_name)
    if not dims:
        raise KeyError(f"no rubric defined for agent '{agent_name}'")
    per_dim: dict[str, list[int]] = {d.name: [] for d in dims}
    for _ in range(runs):
        for ds in judge.score(agent_name, dims, subject):
            if ds.dimension in per_dim:
                per_dim[ds.dimension].append(ds.score)
    medians = {dim: statistics.median(scores) for dim, scores in per_dim.items() if scores}
    return RubricResult(agent_name=agent_name, medians=medians, runs=runs)


class FakeJudge(JudgeGateway):
    """Deterministic judge for tests: scripted per-run score maps (dimension -> 1-5)."""

    def __init__(self, runs: list[dict[str, int]]) -> None:
        self._runs = list(runs)
        self._cursor = 0

    def score(self, agent_name, dimensions, subject) -> list[DimensionScore]:
        run_map = self._runs[self._cursor % len(self._runs)]
        self._cursor += 1
        return [
            DimensionScore(dimension=d.name, score=run_map.get(d.name, 3), rationale="fake")
            for d in dimensions
        ]
