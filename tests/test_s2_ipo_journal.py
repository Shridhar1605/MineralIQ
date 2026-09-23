"""Stage 2 gate (s2): Indian Patent Office Official Journal adapter.

Fixtures are real excerpts of Official Journal No. 38/2026 and of the public
listing page, chosen to cover every IPC and name layout the parser handles.
No network: the harvester's download path is tested only for its refusal
rule, which fires before any request is made.
"""
import json
import pathlib
import sys

import pytest

from ingest.base import patent_key
from ingest.ipo_journal import allowed_file_names, list_journals, parse_journal_text

pytestmark = pytest.mark.s2

ROOT = pathlib.Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "fixtures" / "adapter_samples"
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture(scope="module")
def records():
    text = (SAMPLES / "ipo_journal_excerpt.txt").read_text(encoding="utf-8")
    return {r["appl_no"]: r for r in parse_journal_text(text, "38/2026", "Part I")}


def test_every_record_in_the_excerpt_parses_completely(records):
    assert len(records) == 4
    for r in records.values():
        for field in ("appl_no", "title", "abstract", "applicants", "inventors",
                      "ipc_codes", "filing_date", "publication_date", "source_url"):
            assert r[field], f"{r['appl_no']} missing {field}"
        assert r["source_id"] == "ipo_journal" and r["kind"] == "patent"


def test_ipc_split_across_lines_is_reassembled(records):
    assert records["202611088559"]["ipc_codes"] == [
        "C09B 67/54", "C09B 61/00", "B09B 3/00", "C09B 67/00", "C09B 67/20"]


def test_compact_ipc_and_names_sharing_a_line_with_codes(records):
    r = records["202511023031"]
    assert r["ipc_codes"][:3] == ["B09B 3/00", "F01K 23/06", "F23G 5/20"]
    assert r["applicants"] == ["RAVI KUMAR"]
    assert r["inventors"] == ["RAVI KUMAR", "Mr. Vijay setia"]


def test_inventor_after_the_value_column(records):
    r = records["202511005780"]
    assert r["applicants"] == ["Chaudhary Charan Singh Haryana Agricultural University(CCSHAU)"]
    assert r["inventors"] == ["SINDHU, Sangeeta Chahal", "Sonia"]


def test_long_form_ipc_is_decoded(records):
    codes = records["202511062000"]["ipc_codes"]
    assert codes and all(" " in c and "/" in c for c in codes), codes
    assert not any(len(c.replace(" ", "")) >= 14 for c in codes), "long form left undecoded"


def test_dates_are_iso_and_source_url_is_traceable(records):
    r = records["202611088559"]
    assert r["filing_date"] == "2026-07-21" and r["publication_date"] == "2026-09-18"
    assert r["source_url"].startswith("https://search.ipindia.gov.in/IPOJournal/Journal/Patent#")
    assert r["source_url"].endswith("38/2026/Part-I/202611088559")


def test_application_number_is_the_cross_source_key(records):
    """The Journal publishes the application number itself, which is what
    patent_key() must match across sources (granted patents use a different
    number, see docs/spikes/patent_source.md)."""
    assert patent_key(records["202611088559"]) == "202611088559"


def test_listing_page_yields_journals_and_page_provided_file_names():
    journals = list_journals((SAMPLES / "ipo_listing_excerpt.html").read_text(encoding="utf-8"))
    assert [j["journal_no"] for j in journals] == ["38/2026", "37/2026", "36/2026"]
    first = journals[0]
    assert first["published"] == "18/09/2026"
    labels = [p["label"] for p in first["parts"]]
    assert labels[:2] == ["Part I", "Part II"]
    assert all(p["file_name"].startswith("ipo-docs\\") for p in first["parts"])
    assert len(allowed_file_names(journals)) == sum(len(j["parts"]) for j in journals)


def test_harvester_refuses_a_file_name_the_page_did_not_offer():
    """Guidelines Section 15: FileName is a server path. Submitting one we
    constructed would be unauthorised access, so it must be refused before
    any request is made."""
    import harvest_ipo

    offered = {"ipo-docs\\IPIndia_Docs\\PAT\\2026\\38_2026\\part1.pdf"}
    forged = {"label": "Part I", "file_name": "ipo-docs\\..\\web.config"}
    with pytest.raises(PermissionError):
        harvest_ipo.download_part(forged, offered, pause=0)


def test_only_application_parts_are_fetched_by_default():
    import harvest_ipo

    fetch = lambda label: bool(harvest_ipo.APPLICATION_PART.search(label))
    assert fetch("Part I") and fetch("Part II")
    assert not fetch("Part III") and not fetch("Part IV - Design") and not fetch("Part IV-Designs")


def test_candidate_rule_keeps_mineral_records_and_drops_the_rest(records):
    import harvest_ipo

    assert harvest_ipo.candidate_reason(records["202611088559"]) is None   # textile pigments
    battery = {"title": "Anode for lithium secondary battery", "abstract": "",
               "ipc_codes": ["H01M 4/36"]}
    why = harvest_ipo.candidate_reason(battery)
    assert why == {"keywords": ["lithium"], "ipc": ["H01M"]}


def test_journal_records_reach_the_record_store(tmp_path, records):
    from search.store import load_harvested_records

    f = tmp_path / "raw_ipo.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in records.values()))
    loaded = load_harvested_records(f)
    assert {r["doc_id"] for r in loaded} == set(records)
    assert all(r["orgs"] for r in loaded), "applicants must resolve to organisations"


def test_rate_gate_spaces_request_starts_across_workers():
    """The <=1 request/second commitment holds however many workers run."""
    import threading
    import time

    import harvest_ipo

    gate = harvest_ipo.RateGate(0.2)
    starts = []
    def worker():
        gate.wait()
        starts.append(time.monotonic())
    threads = [threading.Thread(target=worker) for _ in range(4)]
    for th in threads: th.start()
    for th in threads: th.join()
    starts.sort()
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert all(g >= 0.18 for g in gaps), gaps


def test_rate_gate_backs_off_when_the_server_pushes_back():
    import harvest_ipo

    gate = harvest_ipo.RateGate(1.0)
    assert gate.slow_down() == 2.0 and gate.slow_down() == 4.0
    for _ in range(10):
        gate.slow_down()
    assert gate.interval == 60.0, "spacing must be capped, not grow without bound"


def test_worker_count_is_capped():
    import harvest_ipo

    assert harvest_ipo.MAX_WORKERS <= 8
