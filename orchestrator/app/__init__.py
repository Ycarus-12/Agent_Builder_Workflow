"""Orchestrator spine — the deterministic application layer (orchestrator-contract v1.1.0).

This package is plumbing only: sequencing, routing, gating, validate-and-retry,
and logging. No model judgment lives here. External dependencies (model gateway,
datastore, email, identity) are seams behind the ports/ interfaces.
"""

from .state_machine import Pipeline, Stage
from .invocation import AgentSpec, InputEnvelope, OutputMode, Tier

__all__ = ["Pipeline", "Stage", "AgentSpec", "InputEnvelope", "OutputMode", "Tier"]
