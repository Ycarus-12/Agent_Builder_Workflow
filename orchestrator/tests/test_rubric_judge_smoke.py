"""Key-gated live rubric-judge smoke — skipped unless OPENROUTER_API_KEY is set.

    OPENROUTER_API_KEY=... pytest tests/test_rubric_judge_smoke.py -q
"""

import os

import pytest

from app.config import load_gateway_config
from app.evals.rubric import grade
from app.evals.rubric_judge import OpenRouterJudge
from app.ports.gateway import OpenRouterGateway

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="no OPENROUTER_API_KEY; rubric-judge smoke skipped",
)

_SUBJECT = (
    "Build manifest (code): artifact at repo Ycarus-12/checklist@abc123; AC map ties "
    "each criterion to a file:function; build_facts say 'compiles without errors'; no "
    "verdict language; questions empty."
)


def test_live_judge_scores_build_rubric():
    config = load_gateway_config()
    gateway = OpenRouterGateway(config, {"rubric-judge": (config.conversation_model, 1500)})
    judge = OpenRouterJudge(gateway)
    result = grade(judge, "build-agent", _SUBJECT, runs=1)
    # Every build dimension scored on the 1-5 scale.
    assert result.medians and all(1 <= m <= 5 for m in result.medians.values())
