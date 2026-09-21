"""Metric-baseline drift checking (plan Section 1).

The plan promises: "A later stage fails if an earlier number drops by more
than 2 percentage points for quality metrics or 20% for speed." That rule was
written down in baselines.json as a `tolerance` block and implemented
nowhere — the only baseline-shaped assertion in the suite compared two
hardcoded floats with `==`, which goes red when a metric *improves* and says
nothing when one silently degrades.

This module implements the rule for real:

* **quality** metrics are higher-is-better fractions in 0..1. A drop of more
  than `tolerance.quality_pp` percentage points fails. Improvements never fail.
* **speed** metrics are lower-is-better durations. A rise of more than
  `tolerance.speed_pct` percent fails. Speed-ups never fail.

A metric present now but absent from the baseline is reported as new, not as a
failure, so adding a measurement does not break the build. A metric in the
baseline but missing now IS a failure: it means a measurement silently stopped
being taken.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
BASELINES = ROOT / "baselines.json"

QUALITY, SPEED = "quality", "speed"


def load_baselines(path=None):
    return json.loads(pathlib.Path(path or BASELINES).read_text())


def _tolerances(doc):
    tol = doc.get("tolerance", {})
    return float(tol.get("quality_pp", 2.0)), float(tol.get("speed_pct", 20.0))


def check_drift(current, doc=None, path=None):
    """Compare `current` {name: value} against the recorded baselines.

    Returns {"ok": bool, "failures": [...], "improvements": [...],
             "new": [...], "missing": [...]}.
    """
    doc = doc if doc is not None else load_baselines(path)
    quality_pp, speed_pct = _tolerances(doc)
    recorded = doc.get("metrics", {})

    failures, improvements, new, missing = [], [], [], []

    for name, value in sorted(current.items()):
        if name not in recorded:
            new.append({"metric": name, "value": value})
            continue
        base = recorded[name]
        kind = base.get("kind", QUALITY)
        was, now = float(base["value"]), float(value)
        if kind == QUALITY:
            drop_pp = (was - now) * 100.0
            if drop_pp > quality_pp:
                failures.append({
                    "metric": name, "kind": kind, "baseline": was, "current": now,
                    "detail": f"dropped {drop_pp:.2f} pp, tolerance {quality_pp:.2f} pp"})
            elif now > was:
                improvements.append({"metric": name, "baseline": was, "current": now})
        elif kind == SPEED:
            if was <= 0:
                continue
            rise_pct = (now - was) / was * 100.0
            if rise_pct > speed_pct:
                failures.append({
                    "metric": name, "kind": kind, "baseline": was, "current": now,
                    "detail": f"slower by {rise_pct:.1f}%, tolerance {speed_pct:.1f}%"})
            elif now < was:
                improvements.append({"metric": name, "baseline": was, "current": now})
        else:
            failures.append({"metric": name, "kind": kind, "baseline": was,
                             "current": now, "detail": f"unknown metric kind {kind!r}"})

    for name in sorted(recorded):
        if name not in current:
            missing.append({"metric": name,
                            "detail": "in the baseline but no longer measured"})

    return {"ok": not failures and not missing, "failures": failures,
            "improvements": improvements, "new": new, "missing": missing}


def measure_current():
    """Take the measurements the baseline tracks, from the frozen golden set.

    Deliberately golden-only: harvest volume varies per run, so measuring the
    merged store would make drift depend on when someone last harvested.
    """
    import time

    from classify.lexicon import LexiconClassifier
    from classify.metrics import evaluate_holdout
    from classify.resolve import OrgResolver
    from search.index import SearchIndex
    from search.store import load_golden_records

    fixtures = ROOT / "fixtures"
    records = load_golden_records()
    by_id = {r["fixture_id"]: r for r in records if r.get("fixture_id")}
    holdout = json.loads((fixtures / "holdout_labels.json").read_text())
    clf = LexiconClassifier(ROOT / "taxonomy" / "taxonomy_v1.json")
    report = evaluate_holdout(clf, by_id, holdout)

    aliases = json.loads((fixtures / "org_aliases.json").read_text())
    resolver = OrgResolver(fixtures / "org_aliases.json")
    total = hits = 0
    for canonical, variants in aliases["aliases"].items():
        for variant in variants:
            total += 1
            hits += resolver.resolve(variant) == canonical
    merge_rate = hits / total if total else 0.0

    index = SearchIndex(records)
    start = time.perf_counter()
    for _ in range(50):
        index.search("lithium extraction recycling")
    search_ms = (time.perf_counter() - start) / 50 * 1000

    return {
        "s3.mineral_subset_accuracy": report["mineral"]["subset_accuracy"],
        "s3.mineral_macro_f1": report["mineral"]["macro_f1"],
        "s3.stage_subset_accuracy": report["stage"]["subset_accuracy"],
        "s3.stage_macro_f1": report["stage"]["macro_f1"],
        "s3.org_merge_rate": round(merge_rate, 4),
        "s4.search_ms_avg": round(search_ms, 4),
    }
