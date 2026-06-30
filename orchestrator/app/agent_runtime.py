"""Live agent runners — the model-execution path on top of the spine.

- run_structured_agent: the generic path for every single-output structured agent
  (extraction, triage, ROM, deep-dive, build, QA, security, portfolio, registry-
  maintenance). Builds the named-block envelope and drives the validate-and-retry
  loop (§5).
- run_stack_check: the one tool-using agent — a registry_search chat round-trip,
  then a forced structured finding, validated against the schema.
"""

from __future__ import annotations

import json
from typing import Callable

from jsonschema import Draft202012Validator

from .invocation import AgentSpec, InputEnvelope
from .ports.chat import ChatGateway
from .ports.gateway import ModelGateway
from .registry.source import RegistrySource
from .registry.tool import REGISTRY_SEARCH_TOOL, emit_tool, execute_registry_search
from .retry_loop import DEFAULT_MAX_ATTEMPTS, run_structured

_EMIT_FINDING = "emit_finding"


def run_structured_agent(
    gateway: ModelGateway,
    spec: AgentSpec,
    blocks: dict[str, str],
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    log_event: Callable[[dict], None] | None = None,
) -> dict:
    """Run a single-output structured agent end-to-end and return the validated record."""
    envelope = InputEnvelope(spec=spec, blocks=blocks)
    return run_structured(gateway, envelope, max_attempts=max_attempts, log_event=log_event)


class StackCheckError(RuntimeError):
    pass


def run_stack_check(
    chat_gateway: ChatGateway,
    spec: AgentSpec,
    *,
    intake_record_json: str,
    source: RegistrySource,
    schema: dict,
) -> dict:
    """Drive stack-check's one-tool-call loop, then validate the finding (§3.3, §10.3).

    The model may call registry_search once; the orchestrator runs it and feeds the
    results back, then forces the structured finding. If the model emits the finding
    without searching (empty/young registry intuition), that is honored too.
    """
    envelope = InputEnvelope(spec=spec, blocks={"intake_record": intake_record_json})
    tools = [REGISTRY_SEARCH_TOOL, emit_tool(_EMIT_FINDING, spec.output_schema)]
    messages: list[dict] = [{"role": "user", "content": envelope.render()}]

    turn = chat_gateway.chat(
        agent_name=spec.name,
        system_prompt=spec.system_prompt,
        messages=messages,
        tools=tools,
        tool_choice="auto",
    )

    search = turn.tool_call("registry_search")
    if search is not None:
        result = execute_registry_search(source, search.arguments)
        # Append the assistant's tool call and the tool result, then force the finding.
        messages.append({
            "role": "assistant",
            "tool_calls": [{
                "id": search.id, "type": "function",
                "function": {"name": "registry_search", "arguments": json.dumps(search.arguments)},
            }],
        })
        messages.append({"role": "tool", "tool_call_id": search.id, "content": result})
        turn = chat_gateway.chat(
            agent_name=spec.name,
            system_prompt=spec.system_prompt,
            messages=messages,
            tools=tools,
            tool_choice={"type": "function", "function": {"name": _EMIT_FINDING}},
        )

    emit = turn.tool_call(_EMIT_FINDING)
    raw = json.dumps(emit.arguments) if emit is not None else (turn.content or "")
    try:
        finding = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StackCheckError(f"stack-check did not emit a valid finding: {exc.msg}") from exc

    errors = sorted(Draft202012Validator(schema).iter_errors(finding), key=lambda e: list(e.path))
    if errors:
        locs = "; ".join(f"{'/'.join(str(p) for p in e.path) or '(root)'}: {e.message}" for e in errors)
        raise StackCheckError(f"stack-check finding failed schema validation: {locs}")
    return finding
