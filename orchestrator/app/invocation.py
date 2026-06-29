"""The shared agent-invocation contract (orchestrator-contract §3).

Every agent call obeys one shape: the orchestrator passes a single context
payload composed of named, delimited blocks. Two delimiter styles by tier; two
output modes by agent. No silent injections — anything that reaches the agent is
a declared, named block.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Tier(str, Enum):
    """Drives the delimiter style of the input envelope (§3.1)."""

    SLM = "slm"          # labeled bracket blocks: [Block Name]
    MID = "mid"          # XML-style: <block_name> ... </block_name>
    HIGH = "high"        # XML-style: <block_name> ... </block_name>


class OutputMode(str, Enum):
    """A single agent is one mode or the other, never both (§3.3)."""

    PROSE = "prose"            # human-facing; scanned only for declared handoff signals
    STRUCTURED = "structured"  # machine-facing JSON via constrained decoding


@dataclass(frozen=True)
class AgentSpec:
    """What the orchestrator knows about an agent at the call site.

    `block_names` is the exact, ordered set of blocks this agent declares; the
    orchestrator supplies exactly those, nothing else. `version` + `commit_hash`
    are logged on every call for traceability (§3.4).
    """

    name: str
    version: str
    commit_hash: str
    tier: Tier
    output_mode: OutputMode
    block_names: tuple[str, ...]
    # JSON Schema for the declared structured output; required iff STRUCTURED.
    output_schema: dict | None = None
    # The agent's system-prompt body (loaded from agents/<name>.md). Empty for the
    # in-memory fakes/tests that don't exercise a real model; the real gateway
    # sends it as the system message.
    system_prompt: str = ""

    def __post_init__(self) -> None:
        if self.output_mode is OutputMode.STRUCTURED and self.output_schema is None:
            raise ValueError(f"{self.name}: STRUCTURED agents must declare output_schema")
        if self.output_mode is OutputMode.PROSE and self.output_schema is not None:
            raise ValueError(f"{self.name}: PROSE agents must not declare output_schema")


@dataclass(frozen=True)
class InputEnvelope:
    """A rendered set of named blocks bound for one agent call."""

    spec: AgentSpec
    blocks: dict[str, str] = field(default_factory=dict)
    # Protocol block added by the validate-and-retry loop only (§5). It is part of
    # the retry contract, not agent content, so it bypasses the declared-block
    # check while still being a named, visible block (never a silent injection).
    retry_feedback: str | None = None

    def __post_init__(self) -> None:
        declared = set(self.spec.block_names)
        supplied = set(self.blocks)
        unknown = supplied - declared
        if unknown:
            # "No silent injections": the orchestrator never sends a block the
            # agent did not declare.
            raise ValueError(
                f"{self.spec.name}: undeclared block(s) {sorted(unknown)}; "
                f"declared={sorted(declared)}"
            )

    def render(self) -> str:
        """Serialize the supplied blocks using the agent's tier delimiter style.

        Blocks are emitted in the agent's declared order; a declared-but-missing
        block is simply omitted (the orchestrator attaches per the context
        policy, §3.2, which may legitimately skip a block for a given stage).
        """
        parts: list[str] = []
        for name in self.spec.block_names:
            if name not in self.blocks:
                continue
            content = self.blocks[name]
            if self.spec.tier is Tier.SLM:
                parts.append(f"[{name}]\n{content}")
            else:
                parts.append(f"<{name}>\n{content}\n</{name}>")
        if self.retry_feedback is not None:
            if self.spec.tier is Tier.SLM:
                parts.append(f"[Validation feedback]\n{self.retry_feedback}")
            else:
                parts.append(
                    f"<validation_feedback>\n{self.retry_feedback}\n</validation_feedback>"
                )
        return "\n\n".join(parts)

    def with_feedback(self, feedback: str) -> "InputEnvelope":
        """Return a copy carrying the retry feedback block (§5)."""
        return InputEnvelope(spec=self.spec, blocks=dict(self.blocks), retry_feedback=feedback)
