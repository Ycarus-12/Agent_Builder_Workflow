"""Operational-datastore seam (Airtable in production — context tool decisions).

The application's system of record: request records, pipeline state, gate
decisions, and the audit log. NOT the capability registry (that stays
GitHub-YAML). The AI gateway is never the system of record for audit (§8).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Datastore(ABC):
    """Persistence port for transcripts, structured records, state, and audit."""

    @abstractmethod
    def persist_transcript(self, transcript_reference: str, transcript: str) -> None: ...

    @abstractmethod
    def get_transcript(self, transcript_reference: str) -> str | None: ...

    @abstractmethod
    def store_record(self, request_id: str, record: dict[str, Any]) -> None: ...

    @abstractmethod
    def get_record(self, request_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def set_stage(self, request_id: str, stage: str) -> None: ...

    @abstractmethod
    def append_event(self, event: dict[str, Any]) -> None: ...


class InMemoryDatastore(Datastore):
    """Offline fake; everything kept in process memory for tests and the spine."""

    def __init__(self) -> None:
        self.transcripts: dict[str, str] = {}
        self.records: dict[str, dict[str, Any]] = {}
        self.stages: dict[str, str] = {}
        self.events: list[dict[str, Any]] = []

    def persist_transcript(self, transcript_reference: str, transcript: str) -> None:
        self.transcripts[transcript_reference] = transcript

    def get_transcript(self, transcript_reference: str) -> str | None:
        return self.transcripts.get(transcript_reference)

    def store_record(self, request_id: str, record: dict[str, Any]) -> None:
        self.records[request_id] = record

    def get_record(self, request_id: str) -> dict[str, Any] | None:
        return self.records.get(request_id)

    def set_stage(self, request_id: str, stage: str) -> None:
        self.stages[request_id] = stage

    def append_event(self, event: dict[str, Any]) -> None:
        self.events.append(event)
