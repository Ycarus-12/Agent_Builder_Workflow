from app.agents import (
    intake_record_schema,
    load_intake_conversation_spec,
    load_intake_extraction_spec,
)
from app.invocation import OutputMode, Tier


def test_conversation_spec_loads_real_prompt_body():
    spec = load_intake_conversation_spec()
    assert spec.name == "intake-conversation"
    assert spec.tier is Tier.MID
    assert spec.output_mode is OutputMode.PROSE
    assert spec.block_names == ("requestor_identity", "conversation")
    # Real system prompt body is loaded and is non-trivial...
    assert len(spec.system_prompt) > 200
    # ...and excludes the frontmatter + the artifact-note blockquote.
    assert "agent: intake-conversation" not in spec.system_prompt
    assert "Artifact note" not in spec.system_prompt


def test_extraction_spec_loads_schema_and_body():
    spec = load_intake_extraction_spec()
    assert spec.name == "intake-extraction"
    assert spec.tier is Tier.SLM
    assert spec.output_mode is OutputMode.STRUCTURED
    assert spec.block_names == ("Auto-filled", "TRANSCRIPT")
    assert spec.output_schema is not None
    assert spec.output_schema["title"] == "IntakeRecord"
    assert "agent: intake-extraction" not in spec.system_prompt


def test_intake_record_schema_shape():
    schema = intake_record_schema()
    assert schema["additionalProperties"] is False
    assert "data_sensitivity" in schema["properties"]
    assert schema["properties"]["who_is_affected"]["enum"] == [
        "requestor", "team", "multiple_teams", "customers",
    ]
