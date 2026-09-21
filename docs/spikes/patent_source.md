# Spike: patent source (Google Patents BigQuery dry run FIRST)
Result: NOT YET RUN (needs GCP project). Do not skip the dry run — table is TB-scale.
Dry-run query (bytes scanned only, no export):
SELECT publication_number, title_localized, abstract_localized, assignee, inventor, ipc, publication_date, country_code FROM `patents-public-data.patents.publications` WHERE country_code='IN' AND publication_date BETWEEN 20150101 AND 20261231 LIMIT 100
Then narrow: add keyword filter (lithium|spodumene|brine|rare earth|neodymium|graphite anode|cobalt|nickel laterite|HPAL|solvent extraction) + select only needed columns. If dry run >300 GB → narrow columns/date range, export ONCE to local Parquet, never re-query. Free tier: 1 TB/mo.
Gate relevance: proves 2,000+ patent target is reachable before Week 1 harvester work.
Owner: Hrithik. Date: run before 2 Oct.
