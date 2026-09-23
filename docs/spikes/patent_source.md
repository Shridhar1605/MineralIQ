# Spike: patent source (Google Patents BigQuery dry run FIRST)
Result: NOT YET RUN (needs GCP project). Do not skip the dry run — table is TB-scale.
Dry-run query (bytes scanned only, no export):
SELECT publication_number, title_localized, abstract_localized, assignee, inventor, ipc, publication_date, country_code FROM `patents-public-data.patents.publications` WHERE country_code='IN' AND publication_date BETWEEN 20150101 AND 20261231 LIMIT 100
Then narrow: add keyword filter (lithium|spodumene|brine|rare earth|neodymium|graphite anode|cobalt|nickel laterite|HPAL|solvent extraction) + select only needed columns. If dry run >300 GB → narrow columns/date range, export ONCE to local Parquet, never re-query. Free tier: 1 TB/mo.
Gate relevance: proves 2,000+ patent target is reachable before Week 1 harvester work.
Owner: Hrithik. Date: run before 2 Oct.

## Result, 2026-09-23: Google Patents BigQuery is NOT viable for Indian patents

Run with `scripts/bq_spike.py --volume` plus one diagnostic, 35 GB billed in
total (3.4% of the monthly free tier). Nothing was written to the GCP project.

| Measure | Value |
|---|---|
| Indian publications in `patents.publications` | 83,504 |
| ...with any title at all | 238 |
| ...with an English title | 232 |
| ...matching any pilot mineral term | 0 |
| Indian publications dated 2020 or later | 976 |

By decade, 2010s: 27,305 publications, 169 with a title. The research table
(`google_patents_research.publications`) has the same 83,504 IN rows and zero
pilot matches.

Conclusion: the dataset holds bibliographic stubs for a small fraction of
Indian filings, almost none with titles or abstracts, and is thin after 2020.
It cannot be the primary patent source named in the idea submission. Stage 1
existed to catch exactly this before Week 1; the target in GATES.md must not be
assumed until a replacement source passes the same volume check.

Cost notes kept for any future use: neither table is partitioned or clustered,
so every referenced column is scanned in full regardless of WHERE.
`abstract_localized` alone is 194 GB; the research table's English `abstract`
is 107 GB.

Second finding: Indian granted (B) publications carry a grant number, not the
application number (IN-137586-B belongs to application IN-498CA1973-A). The
Google Patents adapter currently stores publication_number as appl_no, and
patent_key() normalises that, so cross-source dedupe would miss granted
patents. Any adapter must key on the application number.
