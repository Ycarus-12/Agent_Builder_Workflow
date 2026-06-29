"""Canonical vocabulary — implemented VERBATIM from context_06_29.md §5.

These token sets are the machine-facing enums shared across every agent, eval,
and contract. Do not rename or recase the values; the registry, the agent
prompts, and the eval suites all assume these exact strings.
"""

from __future__ import annotations

from enum import Enum


class Route(str, Enum):
    """Option route-type."""

    CONFIGURE = "configure"
    BUILD = "build"
    BUY = "buy"


class Outcome(str, Enum):
    """Triage recommendation — the six-outcome cascade, cheapest filters first."""

    ROUTE_ELSEWHERE = "route_elsewhere"
    DONT_BUILD = "dont_build"
    CONFIGURE = "configure"
    PROCESS_TRAINING_FIX = "process_training_fix"
    BUY = "buy"
    BUILD = "build"


class BuildType(str, Enum):
    """build_type / avenue (underscored; no `instructions-only`)."""

    CODE = "code"
    AGENT_CREATION = "agent_creation"
    CONFIG_APPLIED = "config_applied"
    CONFIG_INSTRUCTIONS = "config_instructions"


class Engine(str, Enum):
    """ai | deterministic."""

    AI = "ai"
    DETERMINISTIC = "deterministic"


class Weight(str, Enum):
    """Carried on each build option; replaces the older `lane` field."""

    LIGHT = "light"
    HEAVY = "heavy"


class DataSensitivity(str, Enum):
    """`unspecified` is treated as sensitive-until-confirmed (see sensitivity.py)."""

    NONE = "none"
    INTERNAL = "internal"
    CUSTOMER = "customer"
    FINANCIAL = "financial"
    REGULATED = "regulated"
    UNSPECIFIED = "unspecified"


class Support(str, Enum):
    """Registry capability support — the hinge into the triage tree."""

    NATIVE = "native"
    CONFIGURABLE = "configurable"
    NOT_SUPPORTED = "not_supported"


class Status(str, Enum):
    """Registry record lifecycle status (Title-Case, per Appendix C)."""

    PLANNED = "Planned"
    IN_BUILD = "In build"
    IN_PILOT = "In pilot"
    IN_USE = "In use"
    DEPRECATED = "Deprecated"


# The intake sign-off marker — the literal string emitted by intake-conversation
# only on explicit requestor confirmation, on the final line.
SIGNOFF_MARKER = "[[INTAKE_SIGNOFF_CONFIRMED]]"

# Outcomes that terminate the request when the Director accepts the triage
# recommendation directly at gate_1a (no deep-dive, no build).
TERMINAL_OUTCOMES = frozenset({Outcome.ROUTE_ELSEWHERE, Outcome.DONT_BUILD})
