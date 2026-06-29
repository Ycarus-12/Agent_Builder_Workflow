"""Deterministic sign-off marker detection (orchestrator-contract §4.3).

The orchestrator detects the intake sign-off marker by EXACT STRING MATCH; it
never parses prose for semantic confirmation. Whether the marker is *justified*
(a prior requestor confirmation) is a conversation hard-fail caught by the eval
harness (§7.3), not something the orchestrator second-guesses at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .enums import SIGNOFF_MARKER


class MarkerMisuse(str, Enum):
    """Why a response carrying the marker was NOT treated as a sign-off."""

    NOT_FINAL_LINE = "not_final_line"
    MULTIPLE_OCCURRENCES = "multiple_occurrences"
    NOT_ALONE_ON_LINE = "not_alone_on_line"


@dataclass(frozen=True)
class MarkerResult:
    """Outcome of scanning one agent response for the sign-off marker."""

    fired: bool
    misuse: MarkerMisuse | None = None

    @property
    def is_misuse(self) -> bool:
        return self.misuse is not None


def detect_signoff(agent_response: str) -> MarkerResult:
    """Scan one agent response for a valid sign-off marker.

    Valid iff the marker appears exactly once, as the final non-empty line, with
    no other content on that line. Any other appearance is logged misuse and the
    turn is treated as ordinary conversation (the caller does NOT advance).
    """
    occurrences = agent_response.count(SIGNOFF_MARKER)
    if occurrences == 0:
        return MarkerResult(fired=False)
    if occurrences > 1:
        return MarkerResult(fired=False, misuse=MarkerMisuse.MULTIPLE_OCCURRENCES)

    non_empty_lines = [line for line in agent_response.splitlines() if line.strip()]
    if not non_empty_lines:  # pragma: no cover - marker counted but no lines is impossible
        return MarkerResult(fired=False, misuse=MarkerMisuse.NOT_FINAL_LINE)

    last_line = non_empty_lines[-1]
    if SIGNOFF_MARKER not in last_line:
        return MarkerResult(fired=False, misuse=MarkerMisuse.NOT_FINAL_LINE)
    if last_line.strip() != SIGNOFF_MARKER:
        return MarkerResult(fired=False, misuse=MarkerMisuse.NOT_ALONE_ON_LINE)

    return MarkerResult(fired=True)


def strip_marker_line(agent_response: str) -> str:
    """Remove the marker's final line so the requestor never sees the token (§4.3)."""
    lines = agent_response.splitlines()
    while lines and (not lines[-1].strip() or lines[-1].strip() == SIGNOFF_MARKER):
        lines.pop()
    return "\n".join(lines).rstrip()
