"""Stage 2 ingestion gate (s2). All checks run against saved sample pages —
never live sites. Regression: s1 tests must still pass (see `make regress`).
"""
import pathlib
import pytest

from ingest.adapters import ADAPTERS
from ingest.base import completeness, dedupe_key
from ingest.pipeline import SAMPLE_FILES, run

pytestmark = pytest.mark.s2

ROOT = pathlib.Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "fixtures" / "adapter_samples"


def _parsed():
    records, stats = run(SAMPLES)
    return records, stats


def test_every_adapter_has_sample_and_parses():
    assert len(ADAPTERS) == 7  # contract: one adapter per Stage-2 source
    for a in ADAPTERS:
        assert (SAMPLES / SAMPLE_FILES[a.source_id]).exists(), a.source_id
        recs = a.run((SAMPLES / SAMPLE_FILES[a.source_id]).read_text())
        assert len(recs) >= 1, f"{a.source_id} parsed zero records"


def test_required_fields_at_least_95_percent_complete():
    for a in ADAPTERS:
        recs = a.run((SAMPLES / SAMPLE_FILES[a.source_id]).read_text())
        assert completeness(recs, a.required) >= 0.95, a.source_id


def test_every_record_carries_provenance():
    records, _ = _parsed()
    assert len(records) >= 10
    for r in records:
        assert r["source_url"].startswith("http"), r
        assert r["fetched_at"], r
        assert r["title"] and r["source_id"]


def test_repeated_harvest_adds_zero_duplicates():
    first, _ = _parsed()
    second, stats = _parsed()
    assert {dedupe_key(r) for r in first} == {dedupe_key(r) for r in second}
    assert stats["total"]["duplicates"] == 0
    assert stats["total"]["deduped"] == len(first)


def test_schema_contract_holds_for_ingested_records():
    import re

    sql = (ROOT / "db" / "schema_v1.sql").read_text()
    assert "UNIQUE (source_id, source_url)" in sql
    records, _ = _parsed()
    keys = [dedupe_key(r) for r in records]
    assert len(keys) == len(set(keys)), "ingest output violates UNIQUE(source_id, source_url)"
    assert re.search(r"fetched_at DATE NOT NULL", sql)
