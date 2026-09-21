"""Check fixtures load + provenance (DB-independent; Stage 1)."""
import json, pathlib
root = pathlib.Path(__file__).resolve().parents[1]
pats = json.loads((root/"fixtures"/"golden_patents.json").read_text())
rds = json.loads((root/"fixtures"/"golden_rd.json").read_text())
assert len(pats) >= 8 and len(rds) >= 4
ids = [r["fixture_id"] for r in pats+rds]
assert len(ids)==len(set(ids))
for r in pats+rds:
    assert r["source_url"].startswith("http") and r["fetched_at"] and r["title"]
print(f"fixtures OK: {len(pats)} patents + {len(rds)} rd = {len(ids)} records")
