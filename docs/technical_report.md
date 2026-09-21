# MineralIQ — Concise Technical Report (CMiH 2026, Problem Statement 02)

Team Musketeers (VIT). All figures below are measured by `make regress` /
`scripts/evaluate.py` on 2026-09-17; provisional items are labelled as such.

## 1. Solution summary
MineralIQ aggregates Indian critical-mineral patents (Google Patents Public
Datasets, WIPO PATENTSCOPE) and R&D activity (CSIR labs, JNARDDC, DST/SERB,
OpenAlex) into one classified, linked, searchable store with trend dashboards,
a mineral×technology heatmap, research-vs-patenting gap analysis and alerts.
InPASS is used for manual legal-status spot checks only (CAPTCHA site, never
scraped — Guidelines §§11/15).

## 2. System architecture (see docs/architecture.mmd)
Sources → per-source adapters → raw JSONL store → cleaning/dedup (UNIQUE
source_id+source_url) → lexicon classification + org resolution → knowledge
graph (record/org/taxonomy nodes; applicant_of, classified_as, cofiled_with)
→ in-memory search index (PG-FTS-compatible weights) → FastAPI → React UI.
Nightly: harvest check → evaluate → graph dump → manifest backup.

## 3. Taxonomy v1
5 pilot minerals (LI, REE, GRA, CO, NI), 6 value-chain stages, 22 process
families with sub-domains (`taxonomy/taxonomy_v1.json`, validated by s1).

## 4. Ingestion (Stage 2, measured)
7 adapters parse saved sample pages (tests never touch live sites):
required-field completeness 100% (gate ≥95%); 14 parsed / 14 deduped /
0 duplicates; repeat harvest adds zero. Live 2,000-record BigQuery export +
5 R&D fetches are Week-1 human-track items (`docs/spikes/`).

## 5. Classification & entity resolution (Stage 3, measured, provisional)
Lexicon baseline on the frozen n=4 hold-out: mineral acc 0.75 / macro-F1 0.80;
stage acc 1.00 / F1 1.00 — reported, NOT gated; thresholds (85%/0.75) enforce
at Week-2 n≥100 after labelling (dual-label 50, ≥80% agreement) and SciBERT
fine-tuning on free GPU. The one miss (cobalt in PAT-CONI-001, absent from its
text) is left standing: tuning keywords to it would violate hold-out hygiene.
Org merge: 100% on the 14-org alias seed (gate ≥90%); top-20 collision-free;
CSIR HQ vs CSIR-NML provably distinct. Graph: 12/12 record nodes, 0 dangling.

## 6. Search & UI (Stage 4, measured)
Ranking title³·applicants²·taxonomy²·abstract¹ (weights isolated for identical
PG-FTS migration). 20/20 golden queries top-1 (frozen contract). Mean search
<1 ms on 12 records (gate <1 s; re-measure at 2,000+). Dashboard totals equal
direct DB counts; heatmap cells reconcile per mineral. React (Search,
Dashboards, Heatmap, Organisations, Gaps) builds clean; Playwright journey
spec saved, live run Week 3.

## 7. Gap analysis & alerts (Stage 5, measured)
5/5 sampled matrix cells match hand calculation. Ranking: gap =
research−patents, emptiest-first tiebreak; collaboration = shared cell, no
prior co-filing. Alerts: fire-once seen-state (synthetic patent fires exactly
1; repeat fires 0). Mentor sign-off on top-3 white spaces: pending (Week 4).

## 8. Results vs proposed KPIs (§13 of idea submission)
| KPI | Target | Status |
|---|---|---|
| Patent/R&D database (5 minerals) | 2,000+ / 1,000+ | infra ready; live harvest Week 1 |
| Classifier accuracy | ≥85% | provisional 75% (n=4); gate at n≥100 |
| Org dedup | ≥90% | 100% on seed |
| Dashboards | trends/orgs/networks | live on seed data |
| Gap matrix | automated | live; 5/5 hand-verified |
| Alerts | working | fire-once verified |
| Open-source deploy docs | JNARDDC-hostable | README + compose + CI |

## 9. Limitations & risks
Seed-scale data (12 golden + 14 samples); no live DB/PG-FTS yet (in-memory
stand-ins with migration-compatible semantics); lexicon English-only, weak on
implicit minerals; short-symbol ambiguity (documented); scale figures
unmeasured until Week-1/3 data lands.

## 10. Cost & roadmap
Open-source stack; 8 GB VM ≈ ₹3–5k/mo prototype, ≈ ₹1–1.5L/yr production.
Roadmap: 5→30 minerals via taxonomy entries; more adapters; NCMM portal/API
integration; alerts e-mail (currently in-app/file state).
