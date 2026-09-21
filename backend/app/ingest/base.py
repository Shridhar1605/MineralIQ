"""Shared ingest primitives (Stage 2). Stdlib only — no new dependencies.

Canonical record keys mirror db/schema_v1.sql columns. Every record MUST carry
source_url + fetched_at (provenance gate); the DB enforces UNIQUE(source_id,
source_url), so dedupe_key() uses the same pair and a repeated harvest can
never insert duplicates.
"""
import html
import re

REQUIRED_PATENT = ["title", "applicants", "filing_date"]
REQUIRED_RD = ["title", "source_url"]
REQUIRED_PUBLICATION = ["title", "source_url"]

_WS = re.compile(r"\s+")


def clean_text(s):
    if s is None:
        return ""
    return _WS.sub(" ", html.unescape(str(s))).strip()


def clean_list(values):
    seen, out = set(), []
    for v in values or []:
        v = clean_text(v)
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def norm_date(s):
    """Accept YYYY-MM-DD, YYYYMMDD (int or str), else return cleaned raw."""
    s = clean_text(s)
    m = re.fullmatch(r"(\d{4})-?(\d{2})-?(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return s


def clean_record(rec):
    rec = dict(rec)
    rec["title"] = clean_text(rec.get("title"))
    rec["abstract"] = clean_text(rec.get("abstract"))
    rec["applicants"] = clean_list(rec.get("applicants"))
    rec["inventors"] = clean_list(rec.get("inventors"))
    rec["ipc_codes"] = clean_list(rec.get("ipc_codes"))
    if rec.get("appl_no"):
        rec["appl_no"] = clean_text(rec["appl_no"]).replace(" ", "").upper()
    if rec.get("filing_date"):
        rec["filing_date"] = norm_date(rec["filing_date"])
    rec["source_url"] = clean_text(rec.get("source_url"))
    rec["fetched_at"] = norm_date(rec.get("fetched_at"))
    return rec


def dedupe_key(rec):
    return (rec.get("source_id"), rec.get("source_url"))


def completeness(records, required):
    """Fraction of required fields that are non-empty, over all records."""
    if not records:
        return 0.0
    hits, total = 0, 0
    for r in records:
        for f in required:
            total += 1
            if r.get(f):
                hits += 1
    return hits / total


class BaseAdapter:
    source_id = "base"
    kind = "rd"
    required = REQUIRED_RD

    def parse(self, raw):
        raise NotImplementedError

    def run(self, raw, source_url_hint="", fetched_at="2026-09-17"):
        records = [clean_record(r) for r in self.parse(raw)]
        for r in records:
            r.setdefault("source_id", self.source_id)
            r.setdefault("kind", self.kind)
            if not r.get("source_url"):
                r["source_url"] = source_url_hint
            if not r.get("fetched_at"):
                r["fetched_at"] = fetched_at
        return records
