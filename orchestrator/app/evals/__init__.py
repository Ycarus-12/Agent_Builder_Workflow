"""Eval harness for the agent prompts (orchestrator-contract §7).

Deterministic assertion engine + fixtures, runnable two ways:
- replay mode: assert over recorded/golden agent outputs — runs every commit, gates
  merges, and negative fixtures prove the gate bites.
- live mode: run the real agent through the gateway, then assert — key-gated.

This phase wires the intake suite (intake-evals v1.0.0); the engine generalizes to
the other eight suites.
"""
