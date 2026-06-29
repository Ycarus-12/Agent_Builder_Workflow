"""Per-stage context attachment — deterministic rule, not model judgment (§3.2).

Context is scaled to what each stage needs (spend tokens where judgment justifies
it): judgment stages get the raw transcript plus the structured extract;
mechanical stages get only the structured extract plus stage-specific inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ContextItem(str, Enum):
    """The attachable context pieces a stage may receive."""

    RAW_TRANSCRIPT = "raw_transcript"
    STRUCTURED_EXTRACT = "structured_extract"
    STACK_CHECK_FINDING = "stack_check_finding"
    TRIAGE_OPTION_LIST = "triage_option_list"
    ROM_OUTPUT = "rom_output"
    SELECTED_OPTIONS = "selected_options"          # Director's gate_1a subset
    DIRECTOR_NOTES = "director_notes"              # on re-triage


@dataclass(frozen=True)
class _Rule:
    items: frozenset[ContextItem]
    judgment: bool  # True = nuance stage (gets raw transcript), False = mechanical


# The rule table, transcribed from §3.2. Stages not listed here default to the
# mechanical rule (structured extract only) until they declare otherwise.
_POLICY: dict[str, _Rule] = {
    "intake_extract": _Rule(
        frozenset({ContextItem.STRUCTURED_EXTRACT}), judgment=False
    ),
    "stack_check": _Rule(
        # Mechanical matching against the registry; structured extract only.
        frozenset({ContextItem.STRUCTURED_EXTRACT}), judgment=False
    ),
    "triage": _Rule(
        # Judgment stage: raw transcript + structured extract (+ stack finding).
        frozenset(
            {
                ContextItem.RAW_TRANSCRIPT,
                ContextItem.STRUCTURED_EXTRACT,
                ContextItem.STACK_CHECK_FINDING,
            }
        ),
        judgment=True,
    ),
    "cost_rom": _Rule(
        # Structured extract + triage's costable option list. NOT the transcript
        # (mechanical per-option classification); NOT the stack finding directly
        # (triage already factored it into the option list).
        frozenset({ContextItem.STRUCTURED_EXTRACT, ContextItem.TRIAGE_OPTION_LIST}),
        judgment=False,
    ),
    "cost_deepdive": _Rule(
        # Full context: extract + transcript + stack finding + ROM output +
        # the Director's selected subset from gate_1a.
        frozenset(
            {
                ContextItem.STRUCTURED_EXTRACT,
                ContextItem.RAW_TRANSCRIPT,
                ContextItem.STACK_CHECK_FINDING,
                ContextItem.ROM_OUTPUT,
                ContextItem.SELECTED_OPTIONS,
            }
        ),
        judgment=True,
    ),
}

_MECHANICAL_DEFAULT = _Rule(frozenset({ContextItem.STRUCTURED_EXTRACT}), judgment=False)


def context_for(stage: str, *, re_triage: bool = False) -> frozenset[ContextItem]:
    """Return the context items to attach for a stage.

    On a re-triage (Director rejected the recommendation at gate_1a), the triage
    stage additionally receives the Director's notes block.
    """
    rule = _POLICY.get(stage, _MECHANICAL_DEFAULT)
    items = set(rule.items)
    if stage == "triage" and re_triage:
        items.add(ContextItem.DIRECTOR_NOTES)
    return frozenset(items)


def is_judgment_stage(stage: str) -> bool:
    return _POLICY.get(stage, _MECHANICAL_DEFAULT).judgment
