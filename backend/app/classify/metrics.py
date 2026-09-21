"""Hold-out scoring (Stage 3). Multi-label subset accuracy + macro-F1.

Empty-label rule: a label that appears in neither gold nor predictions is
*excluded* from the macro average, and the count of such labels is reported.
Scoring it 1.0 (the previous rule) inflated the figure — with five mineral
labels and a seed hold-out exercising two of them, three free 1.0s dominated
the mean and a stage macro-F1 of 1.00 rested on four untested labels.
Scoring it 0.0 would punish an unexercised label just as wrongly. Excluding
it, and saying how many were excluded, is the honest reading.
"""
from .lexicon import LexiconClassifier  # noqa: F401


def score_task(gold, pred, labels):
    n = len(gold)
    subset = sum(1 for g, p in zip(gold, pred) if set(g) == set(p)) / n
    f1s = {}
    for lab in labels:
        tp = sum(1 for g, p in zip(gold, pred) if lab in g and lab in p)
        fp = sum(1 for g, p in zip(gold, pred) if lab not in g and lab in p)
        fn = sum(1 for g, p in zip(gold, pred) if lab in g and lab not in p)
        if tp + fp + fn == 0:
            continue  # unexercised by this hold-out; excluded from the mean
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1s[lab] = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    macro = sum(f1s.values()) / len(f1s) if f1s else 0.0
    return {"n": n, "subset_accuracy": round(subset, 4),
            "macro_f1": round(macro, 4),
            "labels_scored": len(f1s), "labels_unexercised": len(labels) - len(f1s),
            "per_label_f1": {k: round(v, 4) for k, v in f1s.items()}}


def passes_gate(mineral_scores, stage_scores):
    return (mineral_scores["subset_accuracy"] >= 0.85
            and mineral_scores["macro_f1"] >= 0.75
            and stage_scores["subset_accuracy"] >= 0.85
            and stage_scores["macro_f1"] >= 0.75)


def evaluate_holdout(classifier, records_by_id, holdout):
    mineral_labels = sorted({m for r in records_by_id.values() for m in r.get("mineral_ids", [])}
                            | {m for v in holdout["labels"].values() for m in v["mineral_ids"]})
    stage_labels = sorted({s for r in records_by_id.values() for s in r.get("stage_ids", [])}
                          | {s for v in holdout["labels"].values() for s in v["stage_ids"]})
    gold_m, pred_m, gold_s, pred_s = [], [], [], []
    for fid in holdout["test_ids"]:
        r = records_by_id[fid]
        p = classifier.predict(r.get("title", ""), r.get("abstract", ""))
        gold_m.append(holdout["labels"][fid]["mineral_ids"])
        pred_m.append(p["mineral_ids"])
        gold_s.append(holdout["labels"][fid]["stage_ids"])
        pred_s.append(p["stage_ids"])
    mineral = score_task(gold_m, pred_m, mineral_labels)
    stage = score_task(gold_s, pred_s, stage_labels)
    n = len(holdout["test_ids"])
    return {"n": n, "locked": holdout["locked"], "mineral": mineral, "stage": stage,
            "provisional": n < 100,
            "gate": "PROVISIONAL (n<100; thresholds enforce at Week-2 n>=100)"
                    if n < 100 else ("PASS" if passes_gate(mineral, stage) else "FAIL")}
