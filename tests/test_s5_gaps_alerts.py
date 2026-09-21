"""Stage 5 gate (s5): gap matrix hand-check, whitespace rank, collaborations,
alert fire-once semantics. Regression: s1-s4 must still pass.
"""
import json
import pathlib
import pytest

import main as api
from alerts.store import AlertStore

pytestmark = pytest.mark.s5

ROOT = pathlib.Path(api.__file__).resolve().parents[2]


def test_five_sampled_cells_match_hand_calculation():
    """The fixture is hand-computed from the golden records (see its note), so
    it is checked against a matrix built from those records alone. Appending a
    harvested record must not look like a matrix bug. Append-only: >= 5."""
    from analytics.gaps import build_matrix
    from search.store import load_golden_records

    hand = json.loads((ROOT / "fixtures" / "gap_handcheck.json").read_text())
    assert len(hand["cells"]) >= 5
    matrix = build_matrix(load_golden_records())
    for cell in hand["cells"]:
        got = matrix["cells"][cell["mineral"]][cell["stage"]]
        assert got["patents"] == cell["patents"], cell
        assert got["research"] == cell["research"], cell


def test_harvested_records_reach_the_gap_matrix():
    """Harvesting must move the matrix, otherwise Week 1 changes nothing."""
    from analytics.gaps import build_matrix
    from search.store import load_golden_records, load_records

    from search.store import RAW_STORE
    if not RAW_STORE.exists():
        pytest.skip("no harvest on disk; run scripts/harvest.py")
    golden, merged = load_golden_records(), load_records()
    assert len(merged) > len(golden), "a harvest exists but adds nothing to the store"
    gm, mm = build_matrix(golden), build_matrix(merged)
    total = lambda m: sum(c["patents"] + c["research"]
                          for row in m["cells"].values() for c in row.values())
    assert total(mm) > total(gm), "harvested records never reach the matrix"


def test_whitespace_ranking_and_shapes():
    matrix = api.do_matrix()
    assert set(matrix) == {"minerals", "stages", "cells"}
    w = api.do_whitespace(top=10)
    assert set(w) == {"top"} and len(w["top"]) == 10
    gaps = [e["gap"] for e in w["top"]]
    assert gaps == sorted(gaps, reverse=True)
    assert w["top"][0]["gap"] == max(
        c["research"] - c["patents"]
        for row in matrix["cells"].values() for c in row.values())
    for e in w["top"]:
        assert set(e) == {"mineral", "stage", "patents", "research", "gap", "neglected"}
        assert e["neglected"] == (e["patents"] + e["research"] == 0)


def test_collaboration_suggestions_share_cells_without_cofiling():
    c = api.do_collaborations()
    assert set(c) == {"suggestions"}
    recs = api.RECORDS
    cofiled = set()
    for r in recs:
        orgs = sorted(r.get("orgs", []) or [])
        cofiled.update((a, b) for i, a in enumerate(orgs) for b in orgs[i + 1:])
    for s in c["suggestions"]:
        assert (s["org_a"], s["org_b"]) not in cofiled
        assert len(s["shared_cells"]) >= 1


def test_synthetic_patent_fires_exactly_one_alert_then_none(tmp_path):
    store = AlertStore(tmp_path / "alerts.json")
    store.subscribe(mineral="LI")
    new_li = {"doc_id": "SYN-001", "title": "Novel lithium brine adsorbent",
              "abstract": "DLE resin test", "mineral_ids": ["LI"],
              "stage_ids": ["extraction_refining"], "kind": "patent"}
    other = {"doc_id": "SYN-002", "title": "Graphite flotation study",
             "abstract": "flotation tests", "mineral_ids": ["GRA"],
             "stage_ids": ["beneficiation"], "kind": "patent"}
    first = store.check([new_li, other])
    assert len(first) == 1 and first[0]["record_id"] == "SYN-001"
    assert store.check([new_li, other]) == []


def test_existing_api_shapes_unchanged():
    s = api.do_search("lithium")
    assert set(s) == {"query", "elapsed_ms", "count", "results"}
    assert api.do_get_record("PAT-LI-001")["id"] == "PAT-LI-001"
    assert api.do_summary()["totals"]["records"] == len(api.RECORDS)
