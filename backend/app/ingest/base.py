"""Shared ingest primitives (Stage 2). Stdlib only — no new dependencies.

Canonical record keys mirror db/schema_v1.sql columns. Every record MUST carry
source_url + fetched_at (provenance gate); the DB enforces UNIQUE(source_id,
source_url), so dedupe_key() uses the same pair and a repeated harvest can
never insert duplicates.
"""
import datetime
import hashlib
import html
import re

# Provenance is a hard requirement of the plan (Section 4: every record must
# carry its source URL and fetch date so any dashboard figure can be traced),
# so both fields belong in the completeness gate, not just in the DB schema.
_PROVENANCE = ["source_url", "fetched_at"]
REQUIRED_PATENT = ["title", "applicants", "filing_date"] + _PROVENANCE
REQUIRED_RD = ["title"] + _PROVENANCE
REQUIRED_PUBLICATION = ["title"] + _PROVENANCE


def today():
    """Resolved per call. A module-level literal would stamp every future
    harvest with the date the code was written."""
    return datetime.date.today().isoformat()

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


_KIND_CODE = re.compile(r"^(?P<stem>.*\d)(?P<kind>[A-Z]\d?)$")


def patent_key(rec):
    """Cross-source identity for a patent, or None when there is no number.

    dedupe_key((source_id, source_url)) only prevents duplicates *within* a
    source, which is what the DB UNIQUE constraint enforces. The same Indian
    application is published by several sources under different URLs, e.g.
    PATENTSCOPE ...docId=IN201841002345 and Google Patents .../IN201841002345B,
    so without an entity key it is counted twice in every total and every gap
    cell. Normalising strips punctuation, case and the trailing kind code
    (A, B, A1, B2 ...) which marks the publication stage, not the invention.
    """
    raw = clean_text(rec.get("appl_no")).upper()
    raw = re.sub(r"[^A-Z0-9]", "", raw)
    if not raw:
        return None
    m = _KIND_CODE.match(raw)
    if m and len(m.group("stem")) >= 8:
        raw = m.group("stem")
    return raw


def record_id(rec):
    """Stable public id for a harvested record.

    Patents carry an application number, which is the natural key. R&D and
    publication records have none, so the id is derived from the same
    (source_id, source_url) pair that dedupe_key and the DB UNIQUE constraint
    use: the same page always yields the same id, so a repeated harvest
    updates a record rather than creating a second one.
    """
    appl = clean_text(rec.get("appl_no"))
    if appl:
        return appl
    key = "|".join(str(p) for p in dedupe_key(rec))
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    return f"{rec.get('source_id', 'src')}-{digest}"


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

    def run(self, raw, source_url_hint="", fetched_at=None):
        records = [clean_record(r) for r in self.parse(raw)]
        for r in records:
            r.setdefault("source_id", self.source_id)
            r.setdefault("kind", self.kind)
            if not r.get("source_url"):
                r["source_url"] = source_url_hint
            if not r.get("fetched_at"):
                r["fetched_at"] = fetched_at or today()
        return records
