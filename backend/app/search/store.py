"""Record store (Stage 4): golden fixtures + harvested records, classified.

Two tiers, deliberately separate:

* **Golden fixtures** are the frozen, hand-checked set. Their labels are
  authoritative, their count is a contract, and the gate tests assert against
  them through ``load_golden_records()``. They are append-only.
* **The harvested store** (``data/raw_store.jsonl``, written by
  ``scripts/harvest.py``) is live data. Its volume changes every harvest, so
  nothing asserts on its size.

``load_records()`` returns both, deduplicated on ``(source_id, source_url)``
— the same pair the DB UNIQUE constraint enforces — with golden winning any
collision, because a hand-checked label beats a predicted one. That is what
makes a Week-1 harvest show up in search, dashboards, the graph and the gap
matrix instead of landing in a file nothing reads.

Label rule: gold labels win when present; otherwise the lexicon fills in.
Org names are resolved to canonicals at load so API counts never double-count
'CSIR-NML' vs 'National Metallurgical Laboratory'. The PG-backed store plugs
in here in Week 3 (same function signatures, rows instead of files).
"""
import json
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
FIX = ROOT / "fixtures"
GOLDEN_FILES = ("golden_patents.json", "golden_rd.json")
RAW_STORE = ROOT / "data" / "raw_store.jsonl"


def _enricher():
    """Build the classifier, org resolver and taxonomy name map once."""
    from classify.lexicon import LexiconClassifier
    from classify.resolve import OrgResolver

    clf = LexiconClassifier(ROOT / "taxonomy" / "taxonomy_v1.json")
    res = OrgResolver(FIX / "org_aliases.json")
    tax = json.loads((ROOT / "taxonomy" / "taxonomy_v1.json").read_text())
    names = {m["id"]: m["name"] for m in tax["minerals"]}
    names.update({s["id"]: s["name"] for s in tax["value_chain_stages"]})

    def enrich(r, doc_id):
        r = dict(r)
        r["doc_id"] = doc_id
        if not r.get("mineral_ids") or not r.get("stage_ids"):
            p = clf.predict(r.get("title", ""), r.get("abstract", ""))
            r.setdefault("mineral_ids", p["mineral_ids"])
            r.setdefault("stage_ids", p["stage_ids"])
            r.setdefault("process_family_ids", p["process_family_ids"])
        r["orgs"] = sorted({res.resolve(a) for a in r.get("applicants", []) if a})
        r["tax_text"] = " ".join(names.get(i, i) for i in r.get("mineral_ids", [])
                                 + r.get("stage_ids", []))
        return r

    return enrich


def _key(r):
    return (r.get("source_id"), r.get("source_url"))


def _identity(r):
    """What makes two records the same *thing* rather than the same *page*.

    Patents use the normalised application number so the same invention
    published by Google Patents and PATENTSCOPE collapses to one record.
    Everything else falls back to the storage key.
    """
    from ingest.base import patent_key

    if r.get("kind") == "patent":
        pk = patent_key(r)
        if pk:
            return ("patent", pk)
    return ("url",) + _key(r)


def load_golden_records():
    """The frozen, hand-checked set. Gate tests assert against this."""
    enrich = _enricher()
    out = []
    for fp in GOLDEN_FILES:
        for r in json.loads((FIX / fp).read_text()):
            out.append(enrich(r, r.get("fixture_id") or r.get("appl_no")))
    return out


def load_harvested_records(path=None):
    """Records written by the harvest pipeline. Empty when none have run."""
    from ingest.base import record_id

    path = pathlib.Path(path) if path else RAW_STORE
    if not path.exists():
        return []
    enrich = _enricher()
    out = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            out.append(enrich(r, record_id(r)))
    return out


def load_records(include_harvested=None, harvest_path=None):
    """Golden fixtures plus harvested records, golden winning any duplicate.

    Set MINERALIQ_INCLUDE_HARVESTED=0 to serve the frozen set alone, which is
    what the deterministic gate tests need.
    """
    if include_harvested is None:
        include_harvested = os.environ.get("MINERALIQ_INCLUDE_HARVESTED", "1") != "0"
    records = load_golden_records()
    if not include_harvested:
        return records
    seen = {_identity(r) for r in records}
    for r in load_harvested_records(harvest_path):
        ident = _identity(r)
        if ident not in seen:
            seen.add(ident)
            records.append(r)
    return records
