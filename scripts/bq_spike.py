"""Stage 1 patent-source spike: cost-guarded Google Patents export.

Why a dry run is mandatory (plan Section 5, Stage 1 and the risk register):
BigQuery bills on bytes *scanned*, and patents-public-data.patents.publications
is a multi-terabyte table. The free tier is 1 TB per month, so a single naive
`SELECT *` can exhaust the month's quota in one query. This script therefore:

  1. always dry-runs first and prints the estimate,
  2. refuses to bill anything above --budget-gb (default 25),
  3. exports once to local Parquet, after which the pipeline reads the file
     and never re-queries.

Column choice is the main cost lever: the table is columnar, so naming the
handful of fields we need is what keeps the scan small. A WHERE clause on an
unpartitioned column does not reduce bytes scanned.

Usage:
  export GOOGLE_APPLICATION_CREDENTIALS=~/.config/mineraliq/gcp-key.json
  python3 scripts/bq_spike.py --dry-run                 # estimate only
  python3 scripts/bq_spike.py --export --budget-gb 25   # bill and save
"""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROJECT = "mineraliq-509317"
TABLE = "patents-public-data.patents.publications"

# Five pilot minerals. Kept deliberately broad: recall matters more than
# precision here, because the taxonomy classifier does the real filtering
# downstream and anything dropped at query time can never be recovered.
TERMS = [
    "lithium", "spodumene", "brine",
    "rare earth", "neodymium", "praseodymium", "dysprosium", "monazite",
    "graphite", "graphene",
    "cobalt", "nickel", "laterite",
]

QUERY = f"""
SELECT
  publication_number,
  application_number,
  country_code,
  kind_code,
  publication_date,
  filing_date,
  (SELECT text FROM UNNEST(title_localized)    WHERE language = 'en' LIMIT 1) AS title,
  (SELECT text FROM UNNEST(abstract_localized) WHERE language = 'en' LIMIT 1) AS abstract,
  ARRAY(SELECT name FROM UNNEST(assignee_harmonized))                        AS assignees,
  ARRAY(SELECT name FROM UNNEST(inventor_harmonized))                        AS inventors,
  ARRAY(SELECT code FROM UNNEST(ipc))                                        AS ipc_codes
FROM `{TABLE}`
WHERE country_code = 'IN'
  AND publication_date >= 20100101
  AND (
    {" OR ".join(
        f"REGEXP_CONTAINS(LOWER((SELECT text FROM UNNEST(title_localized) WHERE language='en' LIMIT 1)), r'{t}')"
        f" OR REGEXP_CONTAINS(LOWER((SELECT text FROM UNNEST(abstract_localized) WHERE language='en' LIMIT 1)), r'{t}')"
        for t in TERMS)}
  )
"""


RESEARCH = "patents-public-data.google_patents_research.publications"

# Per-mineral title patterns. Title-only on purpose: the research table's
# English `title` column costs ~8.5 GB to scan while `abstract` costs ~107 GB,
# and neither table is partitioned, so a filter never reduces bytes scanned.
PILOT = {
    "LI":  r"lithium|spodumene|lepidolite|petalite",
    "REE": r"rare[ -]earth|neodymium|praseodymium|dysprosium|lanthanum|cerium|monazite|samarium|terbium",
    "GRA": r"graphite|graphene",
    "CO":  r"cobalt",
    "NI":  r"nickel|laterite",
}

VOLUME_QUERY = f"""
WITH ind AS (
  SELECT publication_number, LOWER(title) AS t
  FROM `{RESEARCH}`
  WHERE STARTS_WITH(publication_number, 'IN-')
)
SELECT
  COUNT(*) AS in_publications,
  {", ".join(f"COUNTIF(REGEXP_CONTAINS(t, r'{rx}')) AS {m.lower()}" for m, rx in PILOT.items())},
  COUNTIF(REGEXP_CONTAINS(t, r'{"|".join(PILOT.values())}')) AS any_pilot
FROM ind
"""

# Real-data check of the cross-source identity assumption: do Indian granted
# (B) publications carry the application number, or a different grant number?
IDENTITY_PROBE = f"""
SELECT publication_number, application_number, kind_code
FROM `{TABLE}`
WHERE country_code = 'IN' AND STARTS_WITH(kind_code, 'B')
LIMIT 8
"""


def human_gb(n_bytes):
    return n_bytes / 1024 ** 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="estimate only, bill nothing")
    ap.add_argument("--export", action="store_true", help="run for real and save Parquet")
    ap.add_argument("--volume", action="store_true",
                    help="count Indian publications per pilot mineral (title only, ~11 GB)")
    ap.add_argument("--budget-gb", type=float, default=25.0,
                    help="refuse to bill a query estimated above this (default 25)")
    ap.add_argument("--out", default="data/patents_in.parquet")
    args = ap.parse_args()
    if not (args.dry_run or args.export):
        args.dry_run = True

    try:
        from google.cloud import bigquery
        from google.api_core import exceptions
    except ImportError:
        print("pip install google-cloud-bigquery pandas pyarrow")
        return 2

    client = bigquery.Client(project=PROJECT)
    print(f"service account : {client._credentials.service_account_email}")
    print(f"billing project : {client.project}")
    print(f"source table    : {TABLE}")
    print(f"pilot terms     : {len(TERMS)}")

    if args.volume:
        return run_volume(client, bigquery, args.budget_gb)

    try:
        dry = client.query(QUERY, job_config=bigquery.QueryJobConfig(
            dry_run=True, use_query_cache=False))
    except exceptions.Forbidden as exc:
        print("\nFORBIDDEN. The service account cannot create BigQuery jobs.")
        print("Grant it the 'BigQuery Job User' role on this project, then retry:")
        print(f"  gcloud projects add-iam-policy-binding {PROJECT} \\")
        print(f"    --member=serviceAccount:{client._credentials.service_account_email} \\")
        print("    --role=roles/bigquery.jobUser")
        print(f"\n  detail: {str(exc).splitlines()[0][:160]}")
        return 1

    gb = human_gb(dry.total_bytes_processed)
    print(f"\nDRY RUN estimate: {gb:.2f} GB scanned  "
          f"({dry.total_bytes_processed:,} bytes, billed nothing)")
    print(f"free tier        : 1024 GB per month, so this query is "
          f"{gb / 1024 * 100:.1f}% of it")

    spike = ROOT / "docs" / "spikes" / "patent_source.md"
    record = {"estimated_gb": round(gb, 2), "budget_gb": args.budget_gb,
              "table": TABLE, "terms": len(TERMS), "exported": False}

    if not args.export:
        print("\nEstimate only. Re-run with --export to bill and save.")
        print(f"(spike notes: {spike.relative_to(ROOT)})")
        print(json.dumps(record))
        return 0

    if gb > args.budget_gb:
        print(f"\nREFUSING TO RUN: {gb:.2f} GB exceeds the {args.budget_gb} GB budget.")
        print("Narrow the columns, the date range or the term list, or raise --budget-gb "
              "deliberately.")
        return 1

    print(f"\nWithin budget. Running for real ({gb:.2f} GB will be billed) ...")
    rows = client.query(QUERY).to_dataframe()
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    rows.to_parquet(out, index=False)
    record.update(exported=True, rows=len(rows), out=str(out.relative_to(ROOT)))
    print(f"rows            : {len(rows):,}")
    print(f"written         : {out}")
    print("The pipeline reads this file from now on. Do not re-query.")
    print(json.dumps(record))
    return 0


def run_volume(client, bigquery, budget_gb):
    """Stage 1 volume check: dry-run both queries, bill only within budget."""
    total = 0.0
    for name, sql in (("volume", VOLUME_QUERY), ("identity probe", IDENTITY_PROBE)):
        dry = client.query(sql, job_config=bigquery.QueryJobConfig(
            dry_run=True, use_query_cache=False))
        gb = human_gb(dry.total_bytes_processed)
        total += gb
        print(f"dry run {name:15s}: {gb:6.2f} GB")
    print(f"combined         : {total:6.2f} GB  ({total / 1024 * 100:.1f}% of the monthly free tier)")
    if total > budget_gb:
        print(f"REFUSING: over the {budget_gb} GB budget")
        return 1

    row = list(client.query(VOLUME_QUERY).result())[0]
    print("\nIndian publications in Google Patents (all kinds, all years)")
    print(f"  total IN publications : {row['in_publications']:,}")
    for m in PILOT:
        print(f"  {m:4s} title matches     : {row[m.lower()]:,}")
    print(f"  any pilot mineral     : {row['any_pilot']:,}   (target in submission: 2,000+)")

    print("\nIdentity probe: Indian granted (B) publications")
    for r in client.query(IDENTITY_PROBE).result():
        print(f"  {r['publication_number']:22s} application={r['application_number']:22s} kind={r['kind_code']}")
    result = {"billed_gb": round(total, 2), "in_publications": row["in_publications"],
              "per_mineral": {m: row[m.lower()] for m in PILOT}, "any_pilot": row["any_pilot"]}
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
