"""Metric-baseline drift gate (plan Section 1).

Fails when a quality metric has dropped more than tolerance.quality_pp
percentage points, or a speed metric has risen more than tolerance.speed_pct
percent, against the figures recorded in baselines.json.

  python3 scripts/check_drift.py            # check
  python3 scripts/check_drift.py --record   # re-baseline (deliberate act)
"""
import argparse
import collections
import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "app"))

from quality.drift import check_drift, load_baselines, measure_current  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true",
                    help="overwrite the baseline with the current figures")
    args = ap.parse_args()

    current = measure_current()
    if args.record:
        p = ROOT / "baselines.json"
        doc = json.loads(p.read_text(), object_pairs_hook=collections.OrderedDict)
        kinds = {k: v.get("kind", "quality") for k, v in doc.get("metrics", {}).items()}
        doc["metrics"] = collections.OrderedDict(
            (k, {"value": v, "kind": kinds.get(k, "speed" if k.endswith("_ms_avg") else "quality"),
                 "recorded": datetime.date.today().isoformat()})
            for k, v in sorted(current.items()))
        p.write_text(json.dumps(doc, indent=2) + "\n")
        print(f"baseline re-recorded for {len(current)} metrics")
        return 0

    result = check_drift(current, doc=load_baselines())
    qpp = load_baselines().get("tolerance", {}).get("quality_pp", 2.0)
    spct = load_baselines().get("tolerance", {}).get("speed_pct", 20.0)
    print(f"tolerance: quality {qpp} pp, speed {spct}%\n")
    for name, value in sorted(current.items()):
        print(f"  {name:34s} {value}")
    for label, items in (("IMPROVED", result["improvements"]), ("NEW", result["new"])):
        for i in items:
            print(f"\n{label}: {i['metric']}"
                  + (f"  {i['baseline']} -> {i['current']}" if "baseline" in i else ""))
    for f in result["failures"]:
        print(f"\nDRIFT FAIL: {f['metric']}  {f['baseline']} -> {f['current']}  ({f['detail']})")
    for m in result["missing"]:
        print(f"\nDRIFT FAIL: {m['metric']}  {m['detail']}")
    print("\n" + ("OK — no regression beyond tolerance" if result["ok"] else "FAILED"))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
