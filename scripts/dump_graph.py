"""Dump graph node/edge counts (used by nightly). Use: python3 scripts/dump_graph.py [--out data/graph.json]"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend" / "app"))

from classify.resolve import OrgResolver  # noqa: E402
from graph.build import build_graph  # noqa: E402
from search.store import load_records  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="data/graph.json")
args = ap.parse_args()
recs = load_records()
g = build_graph(recs, OrgResolver(ROOT / "fixtures" / "org_aliases.json"))
out = ROOT / args.out
out.write_text(json.dumps({"node_count": len(g["nodes"]), "edge_count": len(g["edges"])}))
print(f"graph dump ok: {len(g['nodes'])} nodes, {len(g['edges'])} edges -> {out}")
