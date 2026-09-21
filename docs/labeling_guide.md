# Week-2 labelling protocol (Stage 3 human-review gate)

## Target
~600 abstracts pre-labelled by the lexicon (`LexiconClassifier`), then
human-reviewed one by one. Labels: mineral_ids, stage_ids, process_family_ids.

## Agreement check (blocks training)
Two people independently label the SAME 50 records. Agreement = exact set
match on mineral_ids AND stage_ids. Required: ≥80% (≥40/50). Below that:
tighten taxonomy definitions (taxonomy_v1.json descriptions + this guide's
edge cases) and re-label — do not train.

## Edge cases
- CSIR HQ ("Council of Scientific and Industrial Research") vs CSIR labs
  (NML/IMMT/CECRI/NEIST): different organisations, never merge.
- Review papers (e.g. "a review"): label by minerals/stages discussed, kind
  stays `publication`.
- Multi-mineral records (battery recycling: LI+CO+NI): label ALL present.
- Recycling vs materials on magnet/battery records: label both stages when
  the text supports both (cf. golden PAT-REE-002).

## Hold-out hygiene
`fixtures/holdout_labels.json` is locked. Expand it to ≥100 by APPENDING new
IDs — never edit existing entries, never tune the lexicon or model against it.
Thresholds (85% acc, 0.75 macro-F1) enforce only at n≥100.
