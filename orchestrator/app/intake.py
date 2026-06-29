"""The intake-specific contract (orchestrator-contract §4).

Manages the stateless conversation loop, deterministic marker detection, and the
one-shot extraction handoff. The intake-conversation agent is prose; the
intake-extraction agent is structured (validated via the retry loop).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .invocation import AgentSpec, InputEnvelope
from .markers import MarkerResult, detect_signoff, strip_marker_line
from .ports.gateway import ModelGateway
from .ports.identity import RequestorIdentity


@dataclass
class ConversationSession:
    """Holds the running conversation buffer (the draft transcript, §4.2)."""

    session_id: str
    identity: RequestorIdentity
    turns: list[tuple[str, str]] = field(default_factory=list)  # (role, content)

    def add_requestor_turn(self, content: str) -> None:
        self.turns.append(("requestor", content))

    def add_agent_turn(self, content: str) -> None:
        self.turns.append(("agent", content))

    def render_conversation(self) -> str:
        return "\n".join(f"{role}: {content}" for role, content in self.turns)


@dataclass
class TurnResult:
    """Outcome of one requestor turn through the conversation loop."""

    visible_reply: str            # marker stripped, safe to show the requestor
    marker: MarkerResult
    raw_agent_response: str


def run_conversation_turn(
    gateway: ModelGateway,
    spec: AgentSpec,
    session: ConversationSession,
    requestor_message: str,
) -> TurnResult:
    """Process one requestor message (§4.2 steps 2-4).

    Builds the envelope from the constant identity block and the running
    conversation, invokes the prose agent, detects the marker deterministically,
    and appends the turn pair. The caller advances the pipeline only on a *valid*
    marker (TurnResult.marker.fired).
    """
    session.add_requestor_turn(requestor_message)
    blocks = {
        "requestor_identity": f"requestor: {session.identity.requestor}\nteam: {session.identity.team}",
        "conversation": session.render_conversation(),
    }
    envelope = InputEnvelope(spec=spec, blocks=blocks)
    raw = gateway.complete(envelope)
    marker = detect_signoff(raw)
    visible = strip_marker_line(raw) if marker.fired else raw
    session.add_agent_turn(visible if marker.fired else raw)
    return TurnResult(visible_reply=visible, marker=marker, raw_agent_response=raw)


def build_extraction_envelope(
    spec: AgentSpec,
    *,
    auto_filled: dict[str, str],
    transcript: str,
) -> InputEnvelope:
    """The one-shot extraction handoff envelope (§4.4): [Auto-filled] + [TRANSCRIPT]."""
    auto_block = "\n".join(f"{k}: {v}" for k, v in auto_filled.items())
    return InputEnvelope(spec=spec, blocks={"Auto-filled": auto_block, "TRANSCRIPT": transcript})
