"""Chat primitive for tool-using agents (stack-check's registry_search loop).

This is the multi-turn extension of the model seam: unlike `complete()` (one
forced structured output), `chat()` lets the model call a tool, receive the
result, and continue. Kept additive so the simple single-output agents keep using
`complete()` unchanged.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class ChatTurn:
    """One model turn: either tool calls to execute, or final content, or both."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)

    def tool_call(self, name: str) -> ToolCall | None:
        for tc in self.tool_calls:
            if tc.name == name:
                return tc
        return None


class ChatGateway(ABC):
    """A gateway that supports a tool-use chat round-trip."""

    @abstractmethod
    def chat(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
        tool_choice: object = "auto",
    ) -> ChatTurn: ...


class FakeChatGateway(ChatGateway):
    """Deterministic chat gateway: scripted ChatTurns per agent, consumed in order."""

    def __init__(self, scripts: dict[str, list[ChatTurn]] | None = None) -> None:
        self._scripts: dict[str, list[ChatTurn]] = {k: list(v) for k, v in (scripts or {}).items()}
        self._cursor: dict[str, int] = {}
        self.calls: list[dict] = []  # recorded (agent_name, messages, tool_choice)

    def script(self, agent_name: str, turns: list[ChatTurn]) -> None:
        self._scripts[agent_name] = list(turns)
        self._cursor[agent_name] = 0

    def chat(self, *, agent_name, system_prompt, messages, tools, tool_choice="auto") -> ChatTurn:
        self.calls.append({"agent": agent_name, "messages": list(messages), "tool_choice": tool_choice})
        turns = self._scripts.get(agent_name)
        if not turns:
            raise KeyError(f"FakeChatGateway has no script for agent '{agent_name}'")
        idx = self._cursor.get(agent_name, 0)
        if idx >= len(turns):
            raise IndexError(f"FakeChatGateway exhausted script for '{agent_name}'")
        self._cursor[agent_name] = idx + 1
        return turns[idx]
