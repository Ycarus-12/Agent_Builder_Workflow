"""Operational-datastore seam (Airtable in production — context tool decisions).

The application's system of record: request records, pipeline state, gate
decisions, and the audit log. NOT the capability registry (that stays
GitHub-YAML). The AI gateway is never the system of record for audit (§8).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Callable

from ..config import AirtableConfig, load_airtable_config


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


class AirtableError(RuntimeError):
    """Raised on missing config, a transport failure, or a non-2xx Airtable reply."""


class AirtableDatastore(Datastore):
    """Operational datastore over the Airtable REST API (role confirmed by Director).

    Keeps the seam: application code depends only on the Datastore port. Four
    tables back the four collections — transcripts, records, pipeline state, and
    the append-only audit log; structured payloads are stored as JSON text so the
    port's dict contracts round-trip unchanged. Keyed writes upsert (find then
    PATCH/POST); the audit log is append-only (POST). Key + base id come from env,
    never code. `transport` is injectable for tests; in production it lazily
    resolves to httpx (mirrors the gateway/emailer adapters).
    """

    def __init__(
        self,
        config: AirtableConfig | None = None,
        *,
        transport: Callable[..., Any] | None = None,
    ) -> None:
        self._config = config or load_airtable_config()
        self._transport = transport

    # -- port surface -----------------------------------------------------
    def persist_transcript(self, transcript_reference: str, transcript: str) -> None:
        self._upsert(self._config.table_transcripts, "reference", transcript_reference,
                     {"reference": transcript_reference, "body": transcript})

    def get_transcript(self, transcript_reference: str) -> str | None:
        rec = self._find(self._config.table_transcripts, "reference", transcript_reference)
        return rec["fields"].get("body") if rec else None

    def store_record(self, request_id: str, record: dict[str, Any]) -> None:
        self._upsert(self._config.table_records, "request_id", request_id,
                     {"request_id": request_id, "payload": json.dumps(record)})

    def get_record(self, request_id: str) -> dict[str, Any] | None:
        rec = self._find(self._config.table_records, "request_id", request_id)
        if not rec:
            return None
        payload = rec["fields"].get("payload")
        return json.loads(payload) if payload else None

    def set_stage(self, request_id: str, stage: str) -> None:
        self._upsert(self._config.table_state, "request_id", request_id,
                     {"request_id": request_id, "stage": stage})

    def append_event(self, event: dict[str, Any]) -> None:
        # Append-only: the audit log never updates a prior row.
        self._create(self._config.table_events,
                     {"request_id": str(event.get("request_id") or ""), "payload": json.dumps(event)})

    # -- Airtable plumbing ------------------------------------------------
    def _find(self, table: str, field: str, value: str) -> dict[str, Any] | None:
        formula = '{%s} = "%s"' % (field, value.replace("\\", "\\\\").replace('"', '\\"'))
        data = self._req("GET", table, params={"filterByFormula": formula, "maxRecords": 1})
        records = data.get("records", [])
        return records[0] if records else None

    def _upsert(self, table: str, key_field: str, key: str, fields: dict[str, Any]) -> None:
        existing = self._find(table, key_field, key)
        if existing:
            self._req("PATCH", f"{table}/{existing['id']}", json={"fields": fields})
        else:
            self._create(table, fields)

    def _create(self, table: str, fields: dict[str, Any]) -> None:
        self._req("POST", table, json={"fields": fields})

    def _req(self, method: str, path: str, *, params: dict | None = None, json: dict | None = None) -> dict:
        if not self._config.is_configured:
            raise AirtableError("AIRTABLE_API_KEY/AIRTABLE_BASE_ID not set; cannot persist")
        transport = self._transport
        if transport is None:
            import httpx  # lazy: the spine imports without httpx at rest

            transport = httpx.request
        url = f"{self._config.base_url}/v0/{self._config.base_id}/{path}"
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = transport(method, url, headers=headers, params=params, json=json, timeout=30.0)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # transport boundary: surface as a seam error
            raise AirtableError(f"airtable {method} {path} failed: {exc}") from exc
