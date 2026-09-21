"""Research-vs-patenting intensity matrix + whitespace ranking (Stage 5).

Cell (mineral, stage): patents = kind=='patent' count, research =
kind in ('rd','publication') count. Ranking rule (documented, hand-checkable):
gap = research - patents (positive = under-patented); sort by gap desc, then
by total asc so empty (neglected) cells surface above merely balanced ones.
Full 5x6 grid is ranked — zeros are data, not omissions.
"""
from itertools import combinations

RESEARCH_KINDS = ("rd", "publication")


def build_matrix(records, minerals=None, stages=None):
    minerals = minerals or sorted({m for r in records for m in r.get("mineral_ids", [])})
    stages = stages or sorted({s for r in records for s in r.get("stage_ids", [])})
    cells = {m: {s: {"patents": 0, "research": 0} for s in stages} for m in minerals}
    for r in records:
        bucket = "research" if r.get("kind") in RESEARCH_KINDS else "patents"
        for m in r.get("mineral_ids", []):
            for s in r.get("stage_ids", []):
                if m in cells and s in cells[m]:
                    cells[m][s][bucket] += 1
    return {"minerals": minerals, "stages": stages, "cells": cells}


def rank_whitespace(matrix):
    ranked = []
    for m in matrix["minerals"]:
        for s in matrix["stages"]:
            c = matrix["cells"][m][s]
            total = c["patents"] + c["research"]
            ranked.append({"mineral": m, "stage": s, "patents": c["patents"],
                           "research": c["research"], "gap": c["research"] - c["patents"],
                           "neglected": total == 0})
    ranked.sort(key=lambda e: (-e["gap"], e["patents"] + e["research"], e["mineral"], e["stage"]))
    return ranked


def collaborations(records):
    activity = {}
    for r in records:
        orgs = r.get("orgs", []) or []
        cells = {(m, s) for m in r.get("mineral_ids", []) for s in r.get("stage_ids", [])}
        for o in orgs:
            activity.setdefault(o, set()).update(cells)
    cofiled = set()
    for r in records:
        for a, b in combinations(sorted(r.get("orgs", []) or []), 2):
            cofiled.add((a, b))
    out = []
    for a, b in combinations(sorted(activity), 2):
        if (a, b) in cofiled:
            continue
        shared = sorted(activity[a] & activity[b])
        if shared:
            out.append({"org_a": a, "org_b": b,
                        "shared_cells": [{"mineral": m, "stage": s} for m, s in shared]})
    return out
