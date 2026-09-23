# DATA_SOURCES.md — every source, licence/terms, access date (Stage-plan §4)
All harvesting respects robots.txt + ≤1 req/s. No CAPTCHA/login bypass. Every record stores source_url + fetched_at.

| Source | Kind | Access | Licence / terms | Date checked |
|---|---|---|---|---|
| Google Patents Public Datasets (BigQuery `patents-public-data`) | patent bulk | BigQuery export, select columns only, export once to Parquet | Google Patents ToS; free tier 1 TB/mo — dry-run first | 2026-09-17 |
| WIPO PATENTSCOPE (IN filings) | patent | Web + API, bibliographic only | WIPO ToS, attribution | 2026-09-17 |
| InPASS (ipindiaservices.gov.in) | patent legal status | MANUAL spot checks only (CAPTCHA site, never scraped) | IPO terms; manual fair use | 2026-09-17 |
| CSIR-NML site + annual reports | rd | requests ≤1/s, PDF via pdfplumber | Public reports, attribution | 2026-09-17 |
| CSIR-IMMT site + annual reports | rd | requests ≤1/s | Public reports, attribution | 2026-09-17 |
| JNARDDC / NCMM portals | rd | requests ≤1/s | Public info, attribution | 2026-09-17 |
| DST / SERB project listings | rd | requests ≤1/s | Public info, attribution | 2026-09-17 |
| OpenAlex / CrossRef | publication metadata | API (check if OpenAlex now needs key — see spike) | CC0 / Crossref ToS | 2026-09-17 |
| PSU annual reports (NALCO/HCL/IREL/KABIL/MECL), Ministry of Mines reports | rd | PDF download | Public reports, attribution | 2026-09-17 |

## Google Patents via BigQuery — access and cost control

Table: `patents-public-data.patents.publications` (Google Patents Public Data,
CC BY 4.0, attribution required in the report and the UI footer).

Billing is on **bytes scanned**, not rows returned, and the table is multi
terabyte. The free tier is 1 TB per calendar month. `scripts/bq_spike.py`
therefore always dry-runs first, prints the estimate, and refuses to bill a
query above `--budget-gb` (default 25). The export is written once to local
Parquet and the pipeline reads that file; the table is never re-queried.

Setup:

1. Service-account key stored outside the repo, mode 600.
2. `GOOGLE_APPLICATION_CREDENTIALS` points at it.
3. The service account needs `roles/bigquery.jobUser` on the billing project.
   Reading the public dataset alone is not enough: creating any job, including
   a dry run, requires that role.

## PRIMARY patent source: Official Journal of the Patent Office (India)

Decided 2026-09-23 after the Google Patents BigQuery spike failed for India
(see docs/spikes/patent_source.md) and the EPO OPS / Lens.org routes required
payment or slow manual approval.

- Publisher: Office of the Controller General of Patents, Designs and Trade
  Marks, Government of India. Weekly, public.
- Listing: https://search.ipindia.gov.in/IPOJournal/Journal/Patent
  (1,031 journals, 39/2005 to date, as of 2026-09-23).
- Access: no login, no CAPTCHA. `robots.txt` on ipindia.gov.in is
  `Disallow:` (empty); search.ipindia.gov.in serves none. Checked 2026-09-23.
- Mechanism: each part is a POST to /IPOJournal/Journal/ViewJournal with a
  hidden FileName the listing page renders. **We only submit FileName values
  read from the page**; a constructed or edited value is refused in code
  before any request (guidelines Section 15). One download at a time, 10 s
  pause, identified User-Agent, every PDF cached so none is fetched twice.
- Content used: Parts I and II (published applications, WIPO INID fields:
  application number, dates, title, IPC, applicants, inventors, abstract).
  Part III (weekly FER lists) and Part IV (designs) are skipped by default.
- Volume, issue 38/2026: 2,753 published applications in Parts I and II,
  about 43 MB, about 2.5 minutes to fetch at the polite pace.
- Parser completeness on that issue: 100% for application number, title,
  abstract, applicants, IPC and dates; 99.3% for inventors (Part II).
- Attribution: "Source: Official Journal of the Patent Office, Government of
  India" in the report and the UI footer.
- Tooling: `scripts/harvest_ipo.py`, parser `backend/app/ingest/ipo_journal.py`,
  requires `pdftotext` (poppler).

Google Patents BigQuery is retained only as a documented negative result.
