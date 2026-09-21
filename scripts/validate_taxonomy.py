"""Validate taxonomy_v1.json against structural rules (no external deps)."""
import json, pathlib, sys
tax = json.loads(pathlib.Path("taxonomy/taxonomy_v1.json").read_text())
errors = []
mids = {m["id"] for m in tax.get("minerals", [])}
sids = {s["id"] for s in tax.get("value_chain_stages", [])}
fids = set()
for f in tax.get("process_families", []):
    fids.add(f["id"])
    if f["stage"] not in sids: errors.append(f"family {f['id']} bad stage {f['stage']}")
    if not f.get("subdomains"): errors.append(f"family {f['id']} has no subdomains")
if {"LI","REE","GRA","CO","NI"} - mids: errors.append("missing pilot minerals")
if len(sids) != 6: errors.append(f"expected 6 stages, got {len(sids)}")
print("TAXONOMY", tax["version"], "minerals:", sorted(mids), "stages:", sorted(sids), "families:", len(fids))
sys.exit(1 if errors else 0)
