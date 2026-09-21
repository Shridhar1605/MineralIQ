"""Offline harvest pipeline (Stage 2): samples -> raw store -> cleaned -> deduped.

Runs ONLY against fixtures/adapter_samples (saved pages). Re-running over the
same samples is idempotent: dedupe on (source_id, source_url) — the same pair
the DB UNIQUE constraint enforces — so a repeated harvest adds zero records.
"""
import json
import pathlib

from .adapters import ADAPTERS
from .base import completeness, dedupe_key

SAMPLE_FILES = {
    "google_patents": "google_patents.jsonl",
    "patentscope": "patentscope.html",
    "csir_nml": "csir_nml.html",
    "csir_immt": "csir_immt.html",
    "jnarddc": "jnarddc.html",
    "dst_serb": "dst_serb.html",
    "openalex": "openalex.json",
}


def run(samples_dir, fetched_at=None):
    """fetched_at defaults to today, resolved per call."""
    samples_dir = pathlib.Path(samples_dir)
    records, stats = [], {}
    for adapter in ADAPTERS:
        raw = (samples_dir / SAMPLE_FILES[adapter.source_id]).read_text()
        parsed = adapter.run(raw, fetched_at=fetched_at)
        stats[adapter.source_id] = {
            "parsed": len(parsed),
            "completeness": round(completeness(parsed, adapter.required), 4),
        }
        records.extend(parsed)
    deduped, seen, dups = [], set(), 0
    for r in records:
        k = dedupe_key(r)
        if k in seen:
            dups += 1
        else:
            seen.add(k)
            deduped.append(r)
    stats["total"] = {"parsed": len(records), "deduped": len(deduped), "duplicates": dups}
    return deduped, stats


def write_raw_store(records, out_path):
    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return out_path
