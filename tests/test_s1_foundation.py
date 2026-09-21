"""Stage 1 foundation gate (s1). All checks run against frozen fixtures, never live sites."""
import json, pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TAX = ROOT / "taxonomy" / "taxonomy_v1.json"
PAT = ROOT / "fixtures" / "golden_patents.json"
RD = ROOT / "fixtures" / "golden_rd.json"
HOLD = ROOT / "fixtures" / "holdout_labels.json"
SCHEMA = ROOT / "db" / "schema_v1.sql"
COMPOSE = ROOT / "docker-compose.yml"

pytestmark = pytest.mark.s1

def test_taxonomy_validates():
    tax = json.loads(TAX.read_text())
    assert tax["version"] == "1.0.0"
    mineral_ids = {m["id"] for m in tax["minerals"]}
    assert {"LI", "REE", "GRA", "CO", "NI"} <= mineral_ids
    stage_ids = {s["id"] for s in tax["value_chain_stages"]}
    assert len(stage_ids) == 6
    fam_stage = {f["id"]: f["stage"] for f in tax["process_families"]}
    assert set(fam_stage.values()) <= stage_ids
    # every family has >=1 subdomain
    for f in tax["process_families"]:
        assert len(f["subdomains"]) >= 1, f["id"]
    # every fixture label must exist in taxonomy
    for fp in (PAT, RD):
        for r in json.loads(fp.read_text()):
            assert set(r.get("mineral_ids", [])) <= mineral_ids, r["fixture_id"]
            assert set(r.get("stage_ids", [])) <= stage_ids, r["fixture_id"]
            if r.get("process_family_ids"):
                assert set(r["process_family_ids"]) <= set(fam_stage), r["fixture_id"]

def test_fixtures_load_and_have_provenance():
    pats = json.loads(PAT.read_text()); rds = json.loads(RD.read_text())
    assert len(pats) >= 8 and len(rds) >= 4  # seed; expand to ~200 in Stage 1
    ids = [r["fixture_id"] for r in pats + rds]
    assert len(ids) == len(set(ids)), "fixture IDs must be unique (append-only)"
    for r in pats + rds:
        assert r["source_url"].startswith("http") and r["fetched_at"]
        assert r["title"] and r["source_id"]

def test_holdout_locked():
    h = json.loads(HOLD.read_text())
    assert h["locked"] is True
    assert len(h["test_ids"]) >= 4
    assert set(h["test_ids"]) <= {r["fixture_id"] for r in json.loads(PAT.read_text()) + json.loads(RD.read_text())}

def test_schema_contract_v1():
    sql = SCHEMA.read_text()
    for obj in ("CREATE TABLE IF NOT EXISTS sources", "CREATE TABLE IF NOT EXISTS records",
                "CREATE TABLE IF NOT EXISTS organisations", "CREATE TABLE IF NOT EXISTS record_org_links",
                "source_url TEXT NOT NULL", "fetched_at DATE NOT NULL", "UNIQUE (source_id, source_url)"):
        assert obj in sql, f"missing contract element: {obj}"

def test_compose_one_command_stack():
    yml = COMPOSE.read_text()
    assert "db:" in yml and "postgres:15-alpine" in yml and "api:" in yml
    assert "/docker-entrypoint-initdb.d/001_schema.sql" in yml

def test_api_health_shape():
    import importlib.util
    spec = importlib.util.spec_from_file_location("main", ROOT / "backend" / "app" / "main.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    body = mod.health()
    assert body == {"status": "ok", "service": "mineraliq-api", "version": "0.1.0"}
