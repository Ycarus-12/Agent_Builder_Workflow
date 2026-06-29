"""FastAPI surface for the orchestrator spine.

Skeleton only in this phase: a health probe and a stage-introspection endpoint.
The real request-driving endpoints arrive when intake is wired end-to-end
through the gateway (build-order Phase 3).
"""

from __future__ import annotations

from fastapi import FastAPI

from .state_machine import DIRECTOR_GATES, Stage

app = FastAPI(title="Tool-Request Orchestrator", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "contract": "orchestrator-contract v1.1.0"}


@app.get("/stages")
def stages() -> dict[str, object]:
    """Expose the pipeline stages and the Director gate stop-points."""
    return {
        "stages": [s.value for s in Stage],
        "director_gates": [s.value for s in DIRECTOR_GATES],
    }
