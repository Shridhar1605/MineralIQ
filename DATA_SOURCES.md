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
