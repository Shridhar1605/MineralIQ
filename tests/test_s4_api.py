"""Stage 4 gate (s4): search API contract, golden queries, dashboards.

Regression: s1-s3 must still pass. Post-index classifier check: lexicon
metrics recomputed here must equal baselines.json s3 figures (merge/classify
hold after re-index). Browser coverage: API journey test now; Playwright spec
(tests/browser/search.spec.js) runs against the live stack in Week 3.
"""
import json
import pathlib
import time
import pytest

import main as api
from classify.lexicon import LexiconClassifier
from classify.metrics import evaluate_holdout

pytestmark = pytest.mark.s4

ROOT = pathlib.Path(api.__file__).resolve().parents[2]


def test_api_contract_shapes():
    s = api.do_search("lithium")
    assert set(s) == {"query", "elapsed_ms", "count", "results"}
    assert set(s["results"][0]) == {"id", "title", "kind", "minerals",
                                    "stages", "applicants", "score"}
    rec = api.do_get_record("PAT-LI-001")
    assert set(rec) == {"id", "title", "abstract", "kind", "minerals", "stages",
                        "families", "applicants", "orgs", "filing_date",
                        "legal_status", "source_id", "source_url"}
    summ = api.do_summary()
    assert set(summ) == {"totals", "by_mineral", "by_stage", "top_orgs"}
    assert set(summ["totals"]) == {"records", "patents", "rd", "publications"}
    heat = api.do_heatmap()
    assert set(heat) == {"minerals", "stages", "cells"}
    org = api.do_org("CSIR-NML")
    assert set(org) == {"org", "record_count", "records", "co_orgs"}
    assert org["org"] == "CSIR-National Metallurgical Laboratory"


def test_golden_queries_return_expected_top():
    """Frozen ranking contract over the golden set.

    Evaluated against the hand-checked fixtures alone, not the merged store:
    harvest volume changes every run, so pinning ranking to it would make a
    legitimate harvest look like a ranking regression. The fixture is
    append-only, hence >= rather than ==.
    """
    from search.index import SearchIndex
    from search.store import load_golden_records

    gq = json.loads((ROOT / "fixtures" / "golden_queries.json").read_text())
    assert len(gq["queries"]) >= 20
    index = SearchIndex(load_golden_records())
    for q in gq["queries"]:
        res = index.search(q["q"], mineral=q.get("mineral"),
                           stage=q.get("stage"), kind=q.get("kind"))
        assert res["results"], q
        assert res["results"][0]["id"] == q["expected_top"], q


def test_harvested_records_are_searchable():
    """A harvest must change what search returns, or ingestion is decorative."""
    from search.index import SearchIndex
    from search.store import load_golden_records, load_records

    golden_ids = {r["doc_id"] for r in load_golden_records()}
    merged = load_records()
    extra = [r for r in merged if r["doc_id"] not in golden_ids]
    from search.store import RAW_STORE
    if not RAW_STORE.exists():
        pytest.skip("no harvest on disk; run scripts/harvest.py")
    assert extra, "a harvest exists on disk but none of it reached the store"
    index = SearchIndex(merged)
    found = set()
    for r in extra:
        hits = index.search(r["title"], limit=50)["results"]
        found.update(h["id"] for h in hits)
    assert found & {r["doc_id"] for r in extra}, "harvested records are not searchable"


def test_search_answers_under_one_second():
    t0 = time.perf_counter()
    for _ in range(20):
        api.do_search("lithium extraction recycling")
    assert (time.perf_counter() - t0) / 20 < 1.0


def test_dashboard_totals_equal_direct_counts():
    summ = api.do_summary()
    recs = api.RECORDS
    assert summ["totals"]["records"] == len(recs)
    assert summ["totals"]["patents"] == sum(1 for r in recs if r["kind"] == "patent")
    assert summ["totals"]["rd"] == sum(1 for r in recs if r["kind"] == "rd")
    assert summ["totals"]["publications"] == sum(1 for r in recs if r["kind"] == "publication")
    heat = api.do_heatmap()
    for m, row in heat["cells"].items():
        expected = sum(len(r.get("stage_ids", [])) for r in recs if m in r.get("mineral_ids", []))
        assert sum(row.values()) == expected, m
    assert heat["minerals"] == sorted(summ["by_mineral"])
    assert heat["stages"] == sorted(summ["by_stage"])


def test_journey_search_to_record_detail():
    res = api.do_search("spodumene")
    doc_id = res["results"][0]["id"]
    detail = api.do_get_record(doc_id)
    assert detail["id"] == doc_id == "PAT-LI-001"
    assert detail["source_url"].startswith("http")


def test_classifier_metrics_hold_after_reindex():
    base = json.loads((ROOT / "baselines.json").read_text())
    holdout = json.loads((ROOT / "fixtures" / "holdout_labels.json").read_text())
    by_id = {}
    for fp in ("golden_patents.json", "golden_rd.json"):
        for r in json.loads((ROOT / "fixtures" / fp).read_text()):
            by_id[r["fixture_id"]] = r
    rep = evaluate_holdout(LexiconClassifier(ROOT / "taxonomy" / "taxonomy_v1.json"),
                           by_id, holdout)
    assert rep["mineral"]["subset_accuracy"] == 0.75
    assert rep["mineral"]["macro_f1"] == 0.8
    assert "s3" in base  # s3 baseline exists to compare against
