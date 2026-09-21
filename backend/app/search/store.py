"""Record store (Stage 4): golden fixtures + pipeline samples, classified.

Label rule: gold labels win when present; otherwise the lexicon fills in.
Org names are resolved to canonicals at load so API counts never double-count
'CSIR-NML' vs 'National Metallurgical Laboratory'. PG-backed store plugs in
here in Week 3 (same function signature, rows instead of fixtures).
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
FIX = ROOT / "fixtures"


def load_records():
    from classify.lexicon import LexiconClassifier
    from classify.resolve import OrgResolver

    clf = LexiconClassifier(ROOT / "taxonomy" / "taxonomy_v1.json")
    res = OrgResolver(FIX / "org_aliases.json")
    tax = json.loads((ROOT / "taxonomy" / "taxonomy_v1.json").read_text())
    names = {m["id"]: m["name"] for m in tax["minerals"]}
    names.update({s["id"]: s["name"] for s in tax["value_chain_stages"]})
    out = []
    for fp in ("golden_patents.json", "golden_rd.json"):
        for r in json.loads((FIX / fp).read_text()):
            r = dict(r)
            r["doc_id"] = r.get("fixture_id") or r.get("appl_no")
            if not r.get("mineral_ids") or not r.get("stage_ids"):
                p = clf.predict(r.get("title", ""), r.get("abstract", ""))
                r.setdefault("mineral_ids", p["mineral_ids"])
                r.setdefault("stage_ids", p["stage_ids"])
                r.setdefault("process_family_ids", p["process_family_ids"])
            r["orgs"] = sorted({res.resolve(a) for a in r.get("applicants", []) if a})
            r["tax_text"] = " ".join(names.get(i, i) for i in r.get("mineral_ids", [])
                                     + r.get("stage_ids", []))
            out.append(r)
    return out
