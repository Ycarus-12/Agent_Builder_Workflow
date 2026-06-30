"""Model-access seam (orchestrator-contract §1, context §6).

All model calls route through this provider-neutral port. Production swaps the
gateway (OpenRouter/BYOK in dev/test -> a compliant gateway in prod) WITHOUT
contract changes. The orchestrator never hardwires a provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict

from ..invocation import InputEnvelope, OutputMode
from .chat import ChatGateway, ChatTurn, ToolCall


class ModelGateway(ABC):
    """Provider-neutral inference port."""

    @abstractmethod
    def complete(self, envelope: InputEnvelope) -> str:
        """Run one inference and return the agent's raw text output.

        For STRUCTURED agents the returned string is the JSON payload produced
        by constrained decoding; validation happens in the retry loop, not here.
        """


class FakeModelGateway(ModelGateway):
    """Deterministic gateway for tests and the spine's offline end-to-end flow.

    Responses are scripted per agent name as an ordered list consumed one call at
    a time, so a retry loop can be driven through fail-then-succeed sequences.
    """

    def __init__(self, scripts: dict[str, list[str]] | None = None) -> None:
        self._scripts: dict[str, list[str]] = {k: list(v) for k, v in (scripts or {}).items()}
        self._cursor: dict[str, int] = defaultdict(int)
        self.calls: list[tuple[str, str]] = []  # (agent_name, rendered_envelope)

    def script(self, agent_name: str, responses: list[str]) -> None:
        self._scripts[agent_name] = list(responses)
        self._cursor[agent_name] = 0

    def complete(self, envelope: InputEnvelope) -> str:
        name = envelope.spec.name
        self.calls.append((name, envelope.render()))
        responses = self._scripts.get(name)
        if not responses:
            raise KeyError(f"FakeModelGateway has no script for agent '{name}'")
        idx = self._cursor[name]
        if idx >= len(responses):
            raise IndexError(
                f"FakeModelGateway exhausted script for '{name}' "
                f"({len(responses)} responses, asked for #{idx + 1})"
            )
        self._cursor[name] += 1
        return responses[idx]


class GatewayError(RuntimeError):
    """Raised on a missing key, transport failure, or a malformed gateway reply."""


# Structured agents emit their record by being forced to call this one tool exactly
# once; the tool's parameter schema IS the agent's declared output schema (§3.3).
_EMIT_TOOL = "emit_record"


class OpenRouterGateway(ModelGateway, ChatGateway):
    """Real provider-neutral adapter: OpenRouter's OpenAI-compatible chat API.

    Single-provider (Anthropic) to start, routed via OpenRouter model namespacing.
    Keeps the ModelGateway seam: application code is unchanged when production
    swaps to a compliant gateway. The API key is read from config (env), never
    hardwired.
    """

    def __init__(self, config, models: dict[str, tuple[str, int]]) -> None:
        # config: app.config.GatewayConfig ; models: agent_name -> (model_id, max_tokens)
        self._config = config
        self._models = models

    def _headers(self) -> dict[str, str]:
        if not self._config.has_key:
            raise GatewayError(
                "OPENROUTER_API_KEY is not set; cannot make a live model call"
            )
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }
        if self._config.http_referer:
            headers["HTTP-Referer"] = self._config.http_referer
        if self._config.app_title:
            headers["X-Title"] = self._config.app_title
        return headers

    def _resolve(self, agent_name: str) -> tuple[str, int]:
        if agent_name not in self._models:
            raise GatewayError(f"no model configured for agent '{agent_name}'")
        return self._models[agent_name]

    def complete(self, envelope: InputEnvelope) -> str:
        import httpx  # imported lazily so the spine imports without httpx at rest

        spec = envelope.spec
        model, max_tokens = self._resolve(spec.name)
        payload: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": spec.system_prompt},
                {"role": "user", "content": envelope.render()},
            ],
        }
        if spec.output_mode is OutputMode.STRUCTURED:
            # Force exactly one tool call whose arguments are the structured record.
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": _EMIT_TOOL,
                        "description": "Emit the structured record matching the schema.",
                        "parameters": spec.output_schema,
                    },
                }
            ]
            payload["tool_choice"] = {
                "type": "function",
                "function": {"name": _EMIT_TOOL},
            }

        try:
            resp = httpx.post(
                f"{self._config.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise GatewayError(f"gateway transport error for '{spec.name}': {exc}") from exc

        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError) as exc:
            raise GatewayError(f"malformed gateway response for '{spec.name}': {data}") from exc

        if spec.output_mode is OutputMode.STRUCTURED:
            try:
                return message["tool_calls"][0]["function"]["arguments"]
            except (KeyError, IndexError) as exc:
                raise GatewayError(
                    f"structured agent '{spec.name}' did not return a tool call: {message}"
                ) from exc
        return message.get("content") or ""

    def chat(self, *, agent_name, system_prompt, messages, tools, tool_choice="auto") -> ChatTurn:
        """One tool-use chat turn (used by the stack-check registry_search loop)."""
        import json

        import httpx

        model, max_tokens = self._resolve(agent_name)
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system_prompt}, *messages],
            "tools": tools,
            "tool_choice": tool_choice,
        }
        try:
            resp = httpx.post(
                f"{self._config.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise GatewayError(f"gateway transport error for '{agent_name}': {exc}") from exc

        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError) as exc:
            raise GatewayError(f"malformed gateway response for '{agent_name}': {data}") from exc

        tool_calls = []
        for tc in message.get("tool_calls") or []:
            fn = tc.get("function", {})
            args = fn.get("arguments", "{}")
            try:
                parsed = json.loads(args) if isinstance(args, str) else (args or {})
            except json.JSONDecodeError:
                parsed = {}
            tool_calls.append(ToolCall(id=tc.get("id", ""), name=fn.get("name", ""), arguments=parsed))
        return ChatTurn(content=message.get("content"), tool_calls=tool_calls)
