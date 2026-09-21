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
    """Classifier quality must not regress when the index is rebuilt.

    Checked against the recorded baseline under the documented tolerance
    rather than by hardcoded equality: `== 0.8` went red whenever a metric
    legitimately moved, which trained everyone to edit the literal, and said
    nothing at all when a metric silently degraded.
    """
    from quality.drift import check_drift, measure_current
    from search.index import SearchIndex

    quality_only = lambda m: {k: v for k, v in m.items() if not k.endswith("_ms_avg")}

    before = measure_current()
    api.INDEX = SearchIndex(api.RECORDS)           # force a rebuild
    after = measure_current()
    # Quality metrics are deterministic, so they must be identical. Timing is
    # not, so it is left to the drift rule and its tolerance.
    assert quality_only(after) == quality_only(before), \
        "rebuilding the index changed classifier metrics"
    result = check_drift(after)
    assert result["ok"], result["failures"] + result["missing"]


def test_metric_baselines_are_machine_readable():
    """The tolerance block existed but nothing read it, and the only
    baseline-shaped check compared two hardcoded floats with ==."""
    from quality.drift import load_baselines

    doc = load_baselines()
    assert doc["tolerance"]["quality_pp"] > 0 and doc["tolerance"]["speed_pct"] > 0
    assert doc.get("metrics"), "no machine-readable metrics recorded"
    for name, entry in doc["metrics"].items():
        assert isinstance(entry["value"], (int, float)), name
        assert entry["kind"] in ("quality", "speed"), name


def test_current_metrics_are_within_baseline_tolerance():
    from quality.drift import check_drift, measure_current

    result = check_drift(measure_current())
    assert result["ok"], result["failures"] + result["missing"]


def test_drift_rule_catches_regressions_and_allows_improvements():
    from quality.drift import check_drift

    doc = {"tolerance": {"quality_pp": 2.0, "speed_pct": 20.0},
           "metrics": {"q": {"value": 0.90, "kind": "quality"},
                       "t": {"value": 100.0, "kind": "speed"}}}
    ok = check_drift({"q": 0.885, "t": 115.0}, doc=doc)          # within tolerance
    assert ok["ok"], ok["failures"]
    bad_q = check_drift({"q": 0.85, "t": 100.0}, doc=doc)        # 5 pp drop
    assert not bad_q["ok"] and bad_q["failures"][0]["metric"] == "q"
    bad_t = check_drift({"q": 0.90, "t": 130.0}, doc=doc)        # 30% slower
    assert not bad_t["ok"] and bad_t["failures"][0]["metric"] == "t"
    better = check_drift({"q": 0.99, "t": 10.0}, doc=doc)        # improvements
    assert better["ok"] and len(better["improvements"]) == 2
    gone = check_drift({"q": 0.90}, doc=doc)                     # stopped measuring
    assert not gone["ok"] and gone["missing"][0]["metric"] == "t"
