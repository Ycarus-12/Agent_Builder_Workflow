"""OpenRouter-backed judge: scores an agent output against a rubric via the gateway.

One grader call returns a 1-5 score + rationale per dimension (structured output).
Used by the weekly / prompt-touch rubric runs; needs a model key. The deterministic
aggregation lives in rubric.py — this is just the judge seam's real implementation.
"""

from __future__ import annotations

from .rubric import DimensionScore, JudgeGateway, RubricDimension
from ..invocation import AgentSpec, InputEnvelope, OutputMode, Tier
from ..ports.gateway import ModelGateway
from ..retry_loop import run_structured

_JUDGE_SYSTEM = (
    "You are a strict evaluation judge. Score the SUBJECT against each rubric "
    "dimension on an integer scale of 1-5 (3 is the pass bar). Base every score on "
    "the subject's actual content; give a one-sentence rationale per dimension. "
    "Return only the structured scores."
)


def _scores_schema(dimensions: tuple[RubricDimension, ...]) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["scores"],
        "properties": {
            "scores": {
                "type": "array",
                "minItems": len(dimensions),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["dimension", "score", "rationale"],
                    "properties": {
                        "dimension": {"type": "string", "enum": [d.name for d in dimensions]},
                        "score": {"type": "integer", "minimum": 1, "maximum": 5},
                        "rationale": {"type": "string", "minLength": 1},
                    },
                },
            }
        },
    }


class OpenRouterJudge(JudgeGateway):
    """Real judge: one structured grader call per run through the model gateway."""

    JUDGE_AGENT = "rubric-judge"

    def __init__(self, gateway: ModelGateway, commit_hash: str = "unknown") -> None:
        self._gateway = gateway
        self._commit_hash = commit_hash

    def score(self, agent_name, dimensions, subject) -> list[DimensionScore]:
        rubric_text = "\n".join(f"- {d.name}: {d.description}" for d in dimensions)
        spec = AgentSpec(
            name=self.JUDGE_AGENT,
            version="1.0.0",
            commit_hash=self._commit_hash,
            tier=Tier.HIGH,
            output_mode=OutputMode.STRUCTURED,
            block_names=("rubric", "subject"),
            output_schema=_scores_schema(dimensions),
            system_prompt=f"{_JUDGE_SYSTEM}\n\nAgent under evaluation: {agent_name}.",
        )
        envelope = InputEnvelope(spec=spec, blocks={"rubric": rubric_text, "subject": subject})
        result = run_structured(self._gateway, envelope, max_attempts=2)
        return [
            DimensionScore(dimension=s["dimension"], score=int(s["score"]), rationale=s["rationale"])
            for s in result["scores"]
        ]
