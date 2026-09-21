"""Offline harvest runner (Stage 2). Default: parse saved samples only.

Live network fetching is NOT performed here. Week-1 live harvest must:
  1. respect robots.txt and <=1 req/s per site (see DATA_SOURCES.md),
  2. never touch InPASS automatically (manual spot checks only),
  3. run BigQuery as a single export to local Parquet (see docs/spikes/patent_source.md).
Use: python3 scripts/harvest.py [--check] [--out data/raw_store.jsonl]
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend" / "app"))

from ingest.adapters import ADAPTERS  # noqa: E402
from ingest.base import completeness  # noqa: E402
from ingest.pipeline import SAMPLE_FILES, run, write_raw_store  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="parse samples, print stats, write nothing")
    ap.add_argument("--out", default="data/raw_store.jsonl")
    args = ap.parse_args()

    samples = ROOT / "fixtures" / "adapter_samples"
    missing = [f for f in SAMPLE_FILES.values() if not (samples / f).exists()]
    if missing:
        print("missing samples:", missing)
        return 1
    records, stats = run(samples)
    for a in ADAPTERS:
        s = stats[a.source_id]
        print(f"{a.source_id:15s} parsed={s['parsed']:3d} completeness={s['completeness']:.1%}")
    t = stats["total"]
    print(f"TOTAL parsed={t['parsed']} deduped={t['deduped']} duplicates={t['duplicates']}")
    if min(stats[a.source_id]["completeness"] for a in ADAPTERS) < 0.95:
        print("GATE FAIL: an adapter is below 95% required-field completeness")
        return 1
    if not args.check:
        out = write_raw_store(records, ROOT / args.out)
        print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
