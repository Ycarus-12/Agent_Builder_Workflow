import pytest

from app.invocation import AgentSpec, InputEnvelope, OutputMode, Tier

PROSE = AgentSpec(
    name="intake-conversation",
    version="1.0.0",
    commit_hash="abc123",
    tier=Tier.MID,
    output_mode=OutputMode.PROSE,
    block_names=("requestor_identity", "conversation"),
)

SLM = AgentSpec(
    name="intake-extraction",
    version="1.0.0",
    commit_hash="abc123",
    tier=Tier.SLM,
    output_mode=OutputMode.STRUCTURED,
    block_names=("Auto-filled", "TRANSCRIPT"),
    output_schema={"type": "object"},
)


def test_xml_delimiters_for_mid_high():
    env = InputEnvelope(spec=PROSE, blocks={"requestor_identity": "x", "conversation": "y"})
    rendered = env.render()
    assert "<requestor_identity>\nx\n</requestor_identity>" in rendered
    assert "<conversation>\ny\n</conversation>" in rendered


def test_bracket_delimiters_for_slm():
    env = InputEnvelope(spec=SLM, blocks={"Auto-filled": "a", "TRANSCRIPT": "t"})
    rendered = env.render()
    assert "[Auto-filled]\na" in rendered
    assert "[TRANSCRIPT]\nt" in rendered


def test_blocks_render_in_declared_order():
    env = InputEnvelope(spec=PROSE, blocks={"conversation": "y", "requestor_identity": "x"})
    rendered = env.render()
    assert rendered.index("requestor_identity") < rendered.index("conversation")


def test_undeclared_block_rejected():
    with pytest.raises(ValueError, match="undeclared block"):
        InputEnvelope(spec=PROSE, blocks={"sneaky": "z"})


def test_missing_block_is_omitted_not_errored():
    env = InputEnvelope(spec=PROSE, blocks={"conversation": "y"})
    rendered = env.render()
    assert "requestor_identity" not in rendered
    assert "conversation" in rendered


def test_retry_feedback_block_renders_last():
    env = InputEnvelope(spec=SLM, blocks={"TRANSCRIPT": "t"}).with_feedback("fix field x")
    rendered = env.render()
    assert "[Validation feedback]\nfix field x" in rendered
    assert rendered.index("TRANSCRIPT") < rendered.index("Validation feedback")


def test_structured_agent_requires_schema():
    with pytest.raises(ValueError, match="must declare output_schema"):
        AgentSpec(
            name="x", version="1", commit_hash="h", tier=Tier.SLM,
            output_mode=OutputMode.STRUCTURED, block_names=(),
        )


def test_prose_agent_must_not_declare_schema():
    with pytest.raises(ValueError, match="must not declare output_schema"):
        AgentSpec(
            name="x", version="1", commit_hash="h", tier=Tier.MID,
            output_mode=OutputMode.PROSE, block_names=(), output_schema={"type": "object"},
        )
