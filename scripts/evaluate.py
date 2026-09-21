"""Score the lexicon baseline on the frozen hold-out (Stage 3).

Report-only: exit 0 always. The 85%/0.75 gate ENFORCES only when the hold-out
reaches n>=100 (Week 2 expansion); on the 4-item seed it prints PROVISIONAL
figures. Use: python3 scripts/evaluate.py [--out data/metrics_s3.json]
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend" / "app"))

from classify.lexicon import LexiconClassifier  # noqa: E402
from classify.metrics import evaluate_holdout  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/metrics_s3.json")
    args = ap.parse_args()
    clf = LexiconClassifier(ROOT / "taxonomy" / "taxonomy_v1.json")
    records = {}
    for fp in ("golden_patents.json", "golden_rd.json"):
        for r in json.loads((ROOT / "fixtures" / fp).read_text()):
            records[r["fixture_id"]] = r
    holdout = json.loads((ROOT / "fixtures" / "holdout_labels.json").read_text())
    report = evaluate_holdout(clf, records, holdout)
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"n={report['n']} locked={report['locked']} gate={report['gate']}")
    print(f"mineral: acc={report['mineral']['subset_accuracy']} F1={report['mineral']['macro_f1']}")
    print(f"stage:   acc={report['stage']['subset_accuracy']} F1={report['stage']['macro_f1']}")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
