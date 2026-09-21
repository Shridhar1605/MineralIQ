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


def test_patent_key_collapses_cross_source_duplicates():
    """The same Indian application is published by several sources under
    different URLs, so (source_id, source_url) cannot catch it. Without an
    entity key the record is counted twice in every total and gap cell."""
    from ingest.base import patent_key

    patentscope = {"appl_no": "IN201841002345"}
    google = {"appl_no": "IN201841002345B"}
    messy = {"appl_no": "in 2018/41002345 a1"}
    assert patent_key(patentscope) == patent_key(google) == patent_key(messy)
    assert patent_key({"appl_no": "IN201941001234A"}) != patent_key(patentscope)
    assert patent_key({"appl_no": ""}) is None
    assert patent_key({}) is None


def test_store_counts_one_patent_per_application():
    """Regression: the golden PATENTSCOPE record and the harvested Google
    Patents record for IN201841002345 must not both appear."""
    from search.store import RAW_STORE, load_records
    from ingest.base import patent_key

    if not RAW_STORE.exists():
        pytest.skip("no harvest on disk; run scripts/harvest.py")
    keys = [patent_key(r) for r in load_records() if r.get("kind") == "patent"]
    keys = [k for k in keys if k]
    assert len(keys) == len(set(keys)), "the same application is counted twice"


def test_institutional_sources_attribute_their_organisation():
    """A CSIR-NML project page has no applicant field; the publishing body is
    the organisation, or organisation analytics would cover patents only."""
    from ingest.adapters import ADAPTERS

    listings = {a.source_id: getattr(a, "organisation", None) for a in ADAPTERS
                if getattr(a, "kind", None) == "rd"}
    assert listings, "no listing adapters found"
    for source_id, org in listings.items():
        assert org, f"{source_id} does not say which organisation it represents"
