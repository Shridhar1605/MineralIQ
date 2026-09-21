import pathlib
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from alerts.store import AlertStore
from analytics.gaps import build_matrix, collaborations, rank_whitespace
from search.index import SearchIndex
from search.store import load_records

app = FastAPI(title="MineralIQ API", version="0.1.0")

# The web app is same-origin in production (the bundle is served below) and
# proxied in dev, so CORS is only needed when the frontend is hosted apart
# from the API. Origins are configurable; the default covers local dev.
_origins = [o for o in os.environ.get(
    "MINERALIQ_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware, allow_origins=_origins, allow_credentials=False,
    allow_methods=["GET", "POST"], allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok", "service": "mineraliq-api", "version": "0.1.0"}

# Module-level store: 12 golden records load in milliseconds. Week 3 swaps
# load_records() for PG rows; handlers below are unchanged.
RECORDS = load_records()
INDEX = SearchIndex(RECORDS)
BY_ID = {r["doc_id"]: r for r in RECORDS}


def do_search(q, mineral=None, stage=None, kind=None, limit=10):
    return INDEX.search(q, mineral=mineral, stage=stage, kind=kind, limit=limit)


def do_get_record(doc_id):
    r = BY_ID.get(doc_id)
    if r is None:
        raise HTTPException(status_code=404, detail="unknown record")
    return {"id": r["doc_id"], "title": r.get("title"), "abstract": r.get("abstract"),
            "kind": r.get("kind"), "minerals": r.get("mineral_ids", []),
            "stages": r.get("stage_ids", []),
            "families": r.get("process_family_ids", []),
            "applicants": r.get("applicants", []), "orgs": r.get("orgs", []),
            "filing_date": r.get("filing_date"), "legal_status": r.get("legal_status"),
            "source_id": r.get("source_id"), "source_url": r.get("source_url")}


def do_summary():
    by_mineral, by_stage, by_kind, by_org = {}, {}, {}, {}
    for r in RECORDS:
        by_kind[r.get("kind")] = by_kind.get(r.get("kind"), 0) + 1
        for m in r.get("mineral_ids", []):
            by_mineral[m] = by_mineral.get(m, 0) + 1
        for s in r.get("stage_ids", []):
            by_stage[s] = by_stage.get(s, 0) + 1
        for o in r.get("orgs", []):
            by_org[o] = by_org.get(o, 0) + 1
    top_orgs = sorted(by_org.items(), key=lambda kv: (-kv[1], kv[0]))
    return {"totals": {"records": len(RECORDS),
                       "patents": by_kind.get("patent", 0),
                       "rd": by_kind.get("rd", 0),
                       "publications": by_kind.get("publication", 0)},
            "by_mineral": by_mineral, "by_stage": by_stage,
            "top_orgs": [{"name": n, "count": c} for n, c in top_orgs]}


def do_heatmap():
    minerals = sorted({m for r in RECORDS for m in r.get("mineral_ids", [])})
    stages = sorted({s for r in RECORDS for s in r.get("stage_ids", [])})
    cells = {m: {s: 0 for s in stages} for m in minerals}
    for r in RECORDS:
        for m in r.get("mineral_ids", []):
            for s in r.get("stage_ids", []):
                cells[m][s] += 1
    return {"minerals": minerals, "stages": stages, "cells": cells}


def do_org(name):
    from classify.resolve import OrgResolver
    import pathlib
    canon = OrgResolver(pathlib.Path(__file__).resolve().parents[2]
                        / "fixtures" / "org_aliases.json").resolve(name)
    recs = [r["doc_id"] for r in RECORDS if canon in r.get("orgs", [])]
    co = sorted({o for r in RECORDS if canon in r.get("orgs", [])
                 for o in r.get("orgs", []) if o != canon})
    if not recs:
        raise HTTPException(status_code=404, detail="unknown organisation")
    return {"org": canon, "record_count": len(recs), "records": recs, "co_orgs": co}


@app.get("/search")
def api_search(q: str = "", mineral: str = None, stage: str = None,
               kind: str = None, limit: int = 10):
    return do_search(q, mineral=mineral, stage=stage, kind=kind, limit=limit)


@app.get("/records/{doc_id}")
def api_record(doc_id: str):
    return do_get_record(doc_id)


@app.get("/dashboard/summary")
def api_summary():
    return do_summary()


@app.get("/heatmap")
def api_heatmap():
    return do_heatmap()


@app.get("/orgs/{name}")
def api_org(name: str):
    return do_org(name)


def do_matrix():
    return build_matrix(RECORDS)


def do_whitespace(top: int = 10):
    return {"top": rank_whitespace(build_matrix(RECORDS))[:top]}


def do_collaborations():
    return {"suggestions": collaborations(RECORDS)}


def _alert_store(path=None):
    root = pathlib.Path(__file__).resolve().parents[2]
    return AlertStore(path or root / "data" / "alerts.json")


def do_subscribe(store, mineral=None, stage=None, kind=None, q="", known_records=None):
    """Seed the subscription with the corpus as it stands, so the subscriber
    hears about what arrives next rather than about everything already held."""
    return store.subscribe(mineral=mineral, stage=stage, kind=kind, q=q,
                           known_records=RECORDS if known_records is None else known_records)


def do_check(store, records=None):
    return {"fired": store.check(records if records is not None else RECORDS)}


@app.get("/gaps/matrix")
def api_matrix():
    return do_matrix()


@app.get("/gaps/whitespace")
def api_whitespace(top: int = 10):
    return do_whitespace(top)


@app.get("/gaps/collaborations")
def api_collaborations():
    return do_collaborations()


@app.post("/alerts/subscribe")
def api_subscribe(body: dict):
    return do_subscribe(_alert_store(), mineral=body.get("mineral"),
                        stage=body.get("stage"), kind=body.get("kind"),
                        q=body.get("q", ""))


@app.post("/alerts/check")
def api_check():
    return do_check(_alert_store())


# Serve the built web app when it exists, so a single container answers both
# the API and the UI. Mounted last: FastAPI matches routes in order, so every
# API route above is resolved before this catch-all.
_DIST = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="web")
