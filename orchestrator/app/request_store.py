"""RequestStore — list and summarize in-flight requests for the Director console.

A thin read view over the Datastore: the runner registers each request id in an
index and persists a snapshot at every stop, so this can enumerate requests and
render a coarse status without rebuilding a runner. The detail view rehydrates a
runner (composition.rehydrate_runner) for the precise pending decision.
"""

from __future__ import annotations

from dataclasses import dataclass

from .pipeline_runner import REQUEST_INDEX_KEY
from .ports.datastore import Datastore
from .state_machine import DIRECTOR_GATES, TERMINAL_STAGES, Stage


@dataclass(frozen=True)
class RequestSummary:
    request_id: str
    stage: str
    request_title: str
    status: str  # awaiting_gate | awaiting_build_input | security_review | running | done
    owner: str | None = None


def owner_key(request_id: str) -> str:
    return f"{request_id}:owner"


def _status_for(pipeline: dict) -> str:
    stage = pipeline.get("stage")
    if stage in {s.value for s in TERMINAL_STAGES}:
        return "done"
    if pipeline.get("awaiting_build_input"):
        return "awaiting_build_input"
    if stage in {s.value for s in DIRECTOR_GATES}:
        return "awaiting_gate"
    if stage == Stage.SECURITY_REVIEW.value:
        return "security_review"
    return "running"


class RequestStore:
    def __init__(self, datastore: Datastore) -> None:
        self.datastore = datastore

    def list_ids(self) -> list[str]:
        index = self.datastore.get_record(REQUEST_INDEX_KEY) or {"request_ids": []}
        return list(index["request_ids"])

    def load_snapshot(self, request_id: str) -> dict | None:
        return self.datastore.get_record(f"{request_id}:snapshot")

    def owner_of(self, request_id: str) -> str | None:
        rec = self.datastore.get_record(owner_key(request_id))
        return rec.get("owner") if rec else None

    def summaries(self, *, owner: str | None = None) -> list[RequestSummary]:
        """All in-flight requests, or only those owned by `owner` (the requestor)."""
        out: list[RequestSummary] = []
        for rid in self.list_ids():
            snap = self.load_snapshot(rid)
            if not snap:
                continue
            rid_owner = self.owner_of(rid)
            if owner is not None and rid_owner != owner:
                continue
            pipeline = snap.get("pipeline", {})
            title = (snap.get("state", {}).get("intake_record") or {}).get("request_title", rid)
            out.append(RequestSummary(
                request_id=rid, stage=pipeline.get("stage", "unknown"),
                request_title=title, status=_status_for(pipeline), owner=rid_owner,
            ))
        return out
