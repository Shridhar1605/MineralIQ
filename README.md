# MineralIQ — Smart Technology & Patent Tracker (CMiH 2026 PS-02)

## Deploy from scratch (teammate clean-machine gate)
1. `cp .env.example .env` (never commit `.env`)
2. `docker compose up --build` — PostgreSQL (+ API on :8000)
3. `make regress` — full cumulative suite must pass
4. Frontend: `cd frontend && npm install && npm run build`
5. Nightly: `0 2 * * * <venv>/bin/python <repo>/scripts/nightly.py`
6. DB backup (live): `pg_dump -Fc mineraliq > data/pg.dump`; file backup: `python3 scripts/backup.py --backup`, verify with `--verify`, restore with `--restore --dest <dir>`

Local checks need only Python+pytest: `make regress`.

## Layout
db/schema_v1.sql (frozen contract) · taxonomy/taxonomy_v1.json · fixtures/ (append-only golden + locked hold-out) · tests/ (markers s1..s6) · backend/app (FastAPI + search + gaps + alerts) · frontend/ (React 5 tabs) · scripts/ (harvest, evaluate, nightly, backup, make_deck) · docs/ (report, architecture.mmd, deck, demo script, checklist).

## Regression
`make regress` runs markers s1→s6 cumulatively. Stage N done only when s1..sN pass. See GATES.md, baselines.json. Feature freeze: only fixes after 28 Oct (Stage 6).
