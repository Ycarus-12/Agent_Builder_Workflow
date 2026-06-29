import json

import pytest

from app.invocation import AgentSpec, InputEnvelope, OutputMode, Tier
from app.ports.gateway import FakeModelGateway
from app.retry_loop import RetryExhausted, run_structured

SCHEMA = {
    "type": "object",
    "required": ["problem", "acceptance_criteria"],
    "properties": {
        "problem": {"type": "string"},
        "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": False,
}

SPEC = AgentSpec(
    name="intake-extraction",
    version="1.0.0",
    commit_hash="deadbeef",
    tier=Tier.SLM,
    output_mode=OutputMode.STRUCTURED,
    block_names=("Auto-filled", "TRANSCRIPT"),
    output_schema=SCHEMA,
)

VALID = json.dumps({"problem": "manual checklist", "acceptance_criteria": ["a", "b"]})


def _env():
    return InputEnvelope(spec=SPEC, blocks={"TRANSCRIPT": "t"})


def test_success_first_attempt():
    gw = FakeModelGateway({"intake-extraction": [VALID]})
    out = run_structured(gw, _env())
    assert out["problem"] == "manual checklist"
    assert len(gw.calls) == 1


def test_success_after_validation_feedback():
    events = []
    gw = FakeModelGateway(
        {"intake-extraction": ['{"problem": "x"}', VALID]}  # first missing required field
    )
    out = run_structured(gw, _env(), log_event=events.append)
    assert out["acceptance_criteria"] == ["a", "b"]
    assert len(gw.calls) == 2
    # The retry envelope carried the [Validation feedback] block.
    assert "Validation feedback" in gw.calls[1][1]
    assert any(e["event"] == "validation_failure" for e in events)


def test_exhaustion_raises_and_escalates():
    events = []
    gw = FakeModelGateway({"intake-extraction": ["{}", "{}", "{}"]})
    with pytest.raises(RetryExhausted) as exc:
        run_structured(gw, _env(), log_event=events.append)
    assert exc.value.agent_name == "intake-extraction"
    assert len(exc.value.attempts) == 3
    assert any(e["event"] == "retry_exhausted" for e in events)


def test_invalid_json_counts_as_failure():
    gw = FakeModelGateway({"intake-extraction": ["not json", VALID]})
    out = run_structured(gw, _env())
    assert out["problem"] == "manual checklist"
    assert len(gw.calls) == 2


def test_prose_agent_rejected():
    prose = AgentSpec(
        name="p", version="1", commit_hash="h", tier=Tier.MID,
        output_mode=OutputMode.PROSE, block_names=(),
    )
    gw = FakeModelGateway({"p": ["x"]})
    with pytest.raises(ValueError, match="requires a STRUCTURED agent"):
        run_structured(gw, InputEnvelope(spec=prose, blocks={}))
