"""AirtableDatastore: port round-trip, upsert vs append-only, no-config guard.

No network — a fake transport implements a tiny in-memory Airtable base
(GET filterByFormula equality, POST create, PATCH update).
"""

import re
from collections import defaultdict

import pytest

from app.config import AirtableConfig
from app.ports.datastore import AirtableDatastore, AirtableError


class _Resp:
    def __init__(self, body: dict, status: int = 200) -> None:
        self._body = body
        self.status = status

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    def json(self) -> dict:
        return self._body


class _FakeAirtable:
    """Minimal Airtable REST stand-in keyed by table name."""

    def __init__(self) -> None:
        self.tables: dict[str, list[dict]] = defaultdict(list)
        self._id = 0

    def request(self, method, url, *, headers, params, json, timeout):
        parts = url.split("/v0/")[1].split("/")
        table = parts[1]
        rec_id = parts[2] if len(parts) > 2 else None

        if method == "GET":
            m = re.match(r'\{(\w+)\} = "(.*)"$', params["filterByFormula"])
            field = m.group(1)
            value = m.group(2).replace('\\"', '"').replace("\\\\", "\\")
            matched = [r for r in self.tables[table] if r["fields"].get(field) == value]
            return _Resp({"records": matched[: params.get("maxRecords", 100)]})
        if method == "POST":
            self._id += 1
            rec = {"id": f"rec{self._id}", "fields": dict(json["fields"])}
            self.tables[table].append(rec)
            return _Resp(rec)
        if method == "PATCH":
            for r in self.tables[table]:
                if r["id"] == rec_id:
                    r["fields"].update(json["fields"])
                    return _Resp(r)
            return _Resp({}, status=404)
        return _Resp({}, status=405)


def _cfg(**over) -> AirtableConfig:
    base = dict(
        base_url="https://api.airtable.com", api_key="pat_test", base_id="appXYZ",
        table_transcripts="Transcripts", table_records="Records",
        table_state="State", table_events="Events",
    )
    base.update(over)
    return AirtableConfig(**base)


def _ds() -> tuple[AirtableDatastore, _FakeAirtable]:
    fake = _FakeAirtable()
    return AirtableDatastore(_cfg(), transport=fake.request), fake


def test_record_round_trips():
    ds, _ = _ds()
    ds.store_record("req-1", {"stage": "build", "n": 1})
    assert ds.get_record("req-1") == {"stage": "build", "n": 1}


def test_missing_record_is_none():
    ds, _ = _ds()
    assert ds.get_record("nope") is None


def test_keyed_writes_upsert_not_duplicate():
    ds, fake = _ds()
    ds.store_record("req-1", {"n": 1})
    ds.store_record("req-1", {"n": 2})  # same key -> update in place
    assert ds.get_record("req-1") == {"n": 2}
    assert len(fake.tables["Records"]) == 1

    ds.set_stage("req-1", "qa_functional")
    ds.set_stage("req-1", "security_review")
    assert len(fake.tables["State"]) == 1
    assert fake.tables["State"][0]["fields"]["stage"] == "security_review"


def test_transcript_round_trips_with_slashes_in_key():
    ds, _ = _ds()
    ds.persist_transcript("txn/2026-06-30/req-1", "Requestor: hi")
    assert ds.get_transcript("txn/2026-06-30/req-1") == "Requestor: hi"


def test_audit_log_is_append_only():
    ds, fake = _ds()
    ds.append_event({"seq": 1, "request_id": "req-1", "event": "agent_call"})
    ds.append_event({"seq": 2, "request_id": "req-1", "event": "gate_decision"})
    assert len(fake.tables["Events"]) == 2  # never coalesced


def test_unconfigured_raises_before_transport():
    touched = []
    ds = AirtableDatastore(
        _cfg(api_key=None, base_id=None), transport=lambda *a, **k: touched.append(1)
    )
    with pytest.raises(AirtableError, match="AIRTABLE_API_KEY/AIRTABLE_BASE_ID"):
        ds.store_record("req-1", {"n": 1})
    assert not touched
