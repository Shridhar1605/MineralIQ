"""In-memory ranked search (Stage 4). Stdlib only.

Semantics mirror the planned PostgreSQL FTS deployment (tsvector over
title^3 + applicants^2 + taxonomy^2 + abstract^1, AND over query tokens):
weights live in WEIGHTS so the PG migration keeps identical ranking.
Filters (mineral/stage/kind) are exact pre-filters, like WHERE clauses.
"""
import re
import time

WEIGHTS = {"title": 3.0, "applicants": 2.0, "tax": 2.0, "abstract": 1.0}
_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text):
    return _TOKEN.findall((text or "").lower())


class SearchIndex:
    def __init__(self, records):
        self.records = records
        self._fields = []
        for r in records:
            self._fields.append({
                "title": set(tokenize(r.get("title"))),
                "applicants": set(tokenize(" ".join(r.get("applicants", [])))),
                "tax": set(tokenize(r.get("tax_text"))),
                "abstract": set(tokenize(r.get("abstract"))),
            })

    def search(self, q, mineral=None, stage=None, kind=None, limit=10):
        t0 = time.perf_counter()
        tokens = tokenize(q)
        hits = []
        for r, f in zip(self.records, self._fields):
            if mineral and mineral not in r.get("mineral_ids", []):
                continue
            if stage and stage not in r.get("stage_ids", []):
                continue
            if kind and kind != r.get("kind"):
                continue
            score = sum(WEIGHTS[k] for t in tokens for k in WEIGHTS if t in f[k])
            if tokens and score == 0:
                continue
            hits.append((score, r))
        hits.sort(key=lambda h: (-h[0], h[1]["doc_id"]))
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return {"query": q, "elapsed_ms": round(elapsed_ms, 3),
                "count": len(hits),
                "results": [{"id": r["doc_id"], "title": r.get("title"),
                             "kind": r.get("kind"), "minerals": r.get("mineral_ids", []),
                             "stages": r.get("stage_ids", []),
                             "applicants": r.get("applicants", []),
                             "score": s} for s, r in hits[:limit]]}
