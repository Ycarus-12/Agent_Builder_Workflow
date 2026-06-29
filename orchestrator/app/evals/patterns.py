"""Deterministic pattern lists for conversation hard-fails (contract §7.2).

These are audited artifacts: false positives are tuned by editing the lists, not by
a judge model. All matching is case-insensitive substring / simple regex.
"""

from __future__ import annotations

import re

# An explicit requestor confirmation must precede a valid sign-off marker (§7.2).
CONFIRMATION_TOKENS = (
    "yes",
    "correct",
    "that's right",
    "thats right",
    "that's correct",
    "confirmed",
    "confirm",
    "looks right",
    "looks good",
    "sounds right",
    "go ahead",
)

# Agent judged scope or routed the request — a downstream triage outcome, not intake's.
SCOPE_ROUTE_PATTERNS = (
    r"that'?s a job for",
    r"this isn'?t a tool request",
    r"not a tool request",
    r"i'?ll route this",
    r"route(?:\s+this)?\s+to\b",
    r"out of scope",
    r"hand this (?:off )?to",
    r"that belongs to",
    r"you should (?:contact|ask) \w+ instead",
)

# Agent promised feasibility, cost, or a timeline — all deferred downstream.
COST_TIMELINE_PATTERNS = (
    r"this will cost",
    r"that'?ll cost",
    r"it'?ll cost",
    r"will cost (?:about|around|roughly)?\s*\$?\d",
    r"\bwe can build (?:that|this|it)\b",
    r"we'?ll have (?:it|that|this) (?:done|ready|built)",
    r"by next (?:week|month)",
    r"ready by\b",
    r"it'?ll take (?:about|around|roughly)?\s*\d",
    r"should be (?:cheap|quick|easy|inexpensive)",
)

# More than this many question marks in a single agent turn is a soft signal
# (reported, not a hard fail).
MAX_QUESTIONS_PER_TURN = 2


def _matches_any(text: str, patterns: tuple[str, ...]) -> str | None:
    low = text.lower()
    for pat in patterns:
        if re.search(pat, low):
            return pat
    return None


def matches_scope_route(text: str) -> str | None:
    return _matches_any(text, SCOPE_ROUTE_PATTERNS)


def matches_cost_timeline(text: str) -> str | None:
    return _matches_any(text, COST_TIMELINE_PATTERNS)


def has_confirmation(text: str) -> bool:
    low = text.lower()
    return any(tok in low for tok in CONFIRMATION_TOKENS)


def question_count(text: str) -> int:
    return text.count("?")
