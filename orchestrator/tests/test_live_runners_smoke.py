"""Key-gated live smokes for the runners — skipped unless OPENROUTER_API_KEY is set.

    OPENROUTER_API_KEY=... pytest tests/test_live_runners_smoke.py -q

Uses only synthetic/sanitized inputs (dev/test rule).
"""

import json
import os

import pytest
from jsonschema import Draft202012Validator

from app.agents import (
    cost_rom_schema,
    load_cost_rom_spec,
    load_stack_check_spec,
    stack_check_finding_schema,
)
from app.agent_runtime import run_stack_check, run_structured_agent
from app.config import load_gateway_config
from app.ports.gateway import OpenRouterGateway
from app.registry.source import InMemoryRegistry

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="no OPENROUTER_API_KEY; live runner smokes skipped",
)

_SANITIZED_REGISTRY = [
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


def _gateway():
    config = load_gateway_config()
    models = {
        "stack-check": (config.conversation_model, 1500),
        "cost-estimation-rom": (config.extraction_model, config.extraction_max_tokens),
    }
    return OpenRouterGateway(config, models)


def test_live_stack_check_tool_loop():
    finding = run_stack_check(
        _gateway(), load_stack_check_spec(),
        intake_record_json=json.dumps({
            "request_title": "Auto-create kickoff checklist on deal close",
            "problem_outcome": "Create a checklist in the work tool when a CRM deal closes.",
            "systems_involved": ["CRM", "work-management tool"],
            "data_sensitivity": "customer",
        }),
        source=InMemoryRegistry(_SANITIZED_REGISTRY),
        schema=stack_check_finding_schema(),
    )
    Draft202012Validator(stack_check_finding_schema()).validate(finding)


def test_live_generic_rom_runner():
    out = run_structured_agent(
        _gateway(), load_cost_rom_spec(),
        {
            "INTAKE RECORD": json.dumps({"request_title": "x", "data_sensitivity": "internal"}),
            "OPTION LIST": json.dumps([
                {"option_id": "opt_001", "route": "configure", "label": "Configure a tool",
                 "tool_name": "Work-Management Tool", "capability_id": "wmt-001-c02"}
            ]),
        },
    )
    Draft202012Validator(cost_rom_schema()).validate(out)
