"""Live-runner tests. The registry_search tool-loop is fully exercised offline via
a fake chat gateway that scripts the tool round-trip — no API key needed."""

import json

from app.agents import load_stack_check_spec, stack_check_finding_schema
from app.agent_runtime import run_stack_check, run_structured_agent
from app.invocation import AgentSpec, OutputMode, Tier
from app.ports.chat import ChatTurn, FakeChatGateway, ToolCall
from app.ports.gateway import FakeModelGateway
from app.registry.source import InMemoryRegistry

_SIMPLE_SPEC = AgentSpec(
    name="demo", version="1.0.0", commit_hash="h", tier=Tier.MID,
    output_mode=OutputMode.STRUCTURED, block_names=("a",),
    output_schema={"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}},
                   "additionalProperties": False},
)

REGISTRY = [
    {
        "id": "wmt-001", "name": "Work-Management Tool", "type": "Tool",
        "category": "Work management", "status": "In use",
        "capabilities": [{
            "id": "wmt-001-c02",
            "statement": "Trigger checklist creation from CRM deal-close events",
            "support": "native", "data_sensitivity": "Customer",
        }],
    }
]

FINDING = {
    "request_title": "Auto-create kickoff checklist on deal close",
    "matches": [{
        "record_id": "wmt-001", "record_name": "Work-Management Tool",
        "capability_id": "wmt-001-c02",
        "capability_statement": "Trigger checklist creation from CRM deal-close events",
        "support": "native", "data_sensitivity_clearance": "customer",
        "relevance_note": "Covers the deal-close checklist trigger.",
    }],
    "no_existing_coverage": False,
    "registry_confidence": "high",
    "finding_summary": "One native match covering the need.",
    "systems_searched": ["CRM", "work-management tool"],
}


def test_generic_structured_runner():
    gw = FakeModelGateway({"demo": [json.dumps({"x": "ok"})]})
    out = run_structured_agent(gw, _SIMPLE_SPEC, {"a": "hello"})
    assert out == {"x": "ok"}


def test_generic_runner_retries_then_succeeds():
    gw = FakeModelGateway({"demo": ['{"y": 1}', json.dumps({"x": "ok"})]})
    out = run_structured_agent(gw, _SIMPLE_SPEC, {"a": "hi"})
    assert out["x"] == "ok"
    assert len(gw.calls) == 2  # one retry after the schema-invalid first attempt


def test_stack_check_tool_loop_runs_registry_search_then_emits():
    spec = load_stack_check_spec()
    chat = FakeChatGateway({
        "stack-check": [
            ChatTurn(tool_calls=[ToolCall("c1", "registry_search",
                                          {"query": "checklist deal close", "systems_filter": ["CRM"]})]),
            ChatTurn(tool_calls=[ToolCall("c2", "emit_finding", FINDING)]),
        ]
    })
    finding = run_stack_check(
        chat, spec,
        intake_record_json=json.dumps({"request_title": "x", "systems_involved": ["CRM"]}),
        source=InMemoryRegistry(REGISTRY),
        schema=stack_check_finding_schema(),
    )
    assert finding["registry_confidence"] == "high"
    assert finding["matches"][0]["capability_id"] == "wmt-001-c02"
    # Two chat turns; the 2nd carries the tool result message with the real registry hit.
    assert len(chat.calls) == 2
    tool_msgs = [m for m in chat.calls[1]["messages"] if m.get("role") == "tool"]
    assert tool_msgs and "wmt-001-c02" in tool_msgs[0]["content"]


def test_stack_check_can_emit_without_searching():
    spec = load_stack_check_spec()
    empty_finding = {**FINDING, "matches": [], "no_existing_coverage": True, "registry_confidence": "empty"}
    chat = FakeChatGateway({
        "stack-check": [ChatTurn(tool_calls=[ToolCall("c1", "emit_finding", empty_finding)])]
    })
    finding = run_stack_check(
        chat, spec, intake_record_json="{}", source=InMemoryRegistry([]),
        schema=stack_check_finding_schema(),
    )
    assert finding["registry_confidence"] == "empty"
    assert len(chat.calls) == 1  # no registry_search round-trip
