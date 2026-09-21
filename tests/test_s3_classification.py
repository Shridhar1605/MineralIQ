"""Stage 3 gate (s3): classification, entity resolution, knowledge graph.

Honesty rule: the frozen hold-out is evaluation-only (n=4 seed). Thresholds
(85% acc / 0.75 macro-F1) ENFORCE only at Week-2 n>=100; until then tests
assert the harness is sound and figures are reported provisionally.
Regression: s1+s2 must still pass (see `make regress`).
"""
import json
import pathlib
import pytest

from classify.lexicon import LexiconClassifier
from classify.metrics import evaluate_holdout, passes_gate
from classify.resolve import OrgResolver, normalize
from graph.build import build_graph, reconcile

pytestmark = pytest.mark.s3

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _golden():
    recs = []
    for fp in ("golden_patents.json", "golden_rd.json"):
        recs += json.loads((ROOT / "fixtures" / fp).read_text())
    return recs


def _clf():
    return LexiconClassifier(ROOT / "taxonomy" / "taxonomy_v1.json")


def test_lexicon_outputs_valid_taxonomy_ids():
    tax = json.loads((ROOT / "taxonomy" / "taxonomy_v1.json").read_text())
    mids = {m["id"] for m in tax["minerals"]}
    sids = {s["id"] for s in tax["value_chain_stages"]}
    fids = {f["id"] for f in tax["process_families"]}
    clf = _clf()
    for r in _golden():
        p = clf.predict(r.get("title", ""), r.get("abstract", ""))
        assert set(p["mineral_ids"]) <= mids, r["fixture_id"]
        assert set(p["stage_ids"]) <= sids, r["fixture_id"]
        assert set(p["process_family_ids"]) <= fids, r["fixture_id"]


def test_holdout_harness_reports_provisional_figures():
    holdout = json.loads((ROOT / "fixtures" / "holdout_labels.json").read_text())
    assert holdout["locked"] is True
    by_id = {r["fixture_id"]: r for r in _golden()}
    rep = evaluate_holdout(_clf(), by_id, holdout)
    assert rep["n"] == len(holdout["test_ids"]) == 4
    for task in ("mineral", "stage"):
        assert 0.0 <= rep[task]["subset_accuracy"] <= 1.0
        assert 0.0 <= rep[task]["macro_f1"] <= 1.0
    assert rep["provisional"] is True
    assert rep["gate"].startswith("PROVISIONAL")


def test_gate_threshold_logic():
    good = {"subset_accuracy": 0.87, "macro_f1": 0.80}
    assert passes_gate(good, good) is True
    assert passes_gate({"subset_accuracy": 0.84, "macro_f1": 0.90}, good) is False
    assert passes_gate(good, {"subset_accuracy": 0.90, "macro_f1": 0.74}) is False


def test_org_merge_accuracy_and_no_collision():
    data = json.loads((ROOT / "fixtures" / "org_aliases.json").read_text())
    res = OrgResolver(ROOT / "fixtures" / "org_aliases.json")
    total, hits = 0, 0
    for canonical, variants in data["aliases"].items():
        for v in [canonical] + variants:
            total += 1
            hits += res.resolve(v) == canonical
    assert hits / total >= 0.90  # gate threshold; seed measures 100%
    assert len(res.top) == 20 and len({normalize(t) for t in res.top}) == 20
    assert res.resolve("Council of Scientific and Industrial Research") != res.resolve("CSIR-NML")


def test_graph_counts_reconcile():
    res = OrgResolver(ROOT / "fixtures" / "org_aliases.json")
    golden = _golden()
    g = build_graph(golden, res)
    ok, rep = reconcile(g, len(golden))
    assert ok, rep
    assert rep["dangling_edges"] == 0
    org_nodes = {f"org:{res.resolve(a)}" for r in golden for a in r.get("applicants", []) if a}
    assert org_nodes <= set(g["nodes"])
    # co-filing logic: two records sharing one org yield exactly one pair edge
    demo = [
        {"fixture_id": "D1", "kind": "patent", "title": "d1", "applicants": ["CSIR-NML", "IIT Bombay"],
         "mineral_ids": ["LI"], "stage_ids": [], "process_family_ids": []},
        {"fixture_id": "D2", "kind": "patent", "title": "d2", "applicants": ["National Metallurgical Laboratory"],
         "mineral_ids": [], "stage_ids": [], "process_family_ids": []},
    ]
    g2 = build_graph(demo, res)
    cofile = [e for e in g2["edges"] if e[2] == "cofiled_with"]
    assert len(cofile) == 1  # CSIR-NML == National Metallurgical Laboratory merged
