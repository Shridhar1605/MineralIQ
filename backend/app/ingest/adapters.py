"""One adapter per source (Stage 2). Each parses SAVED sample pages only —
tests never touch live sites. Live fetching is a Week-1 activity behind
scripts/harvest.py --live with robots.txt + rate-limit guards.

Field mapping notes:
- google_patents: BigQuery `patents-public-data.patents.publications` export
  (one JSON object per line). publication_date/filing_date are YYYYMMDD ints.
- patentscope: saved PATENTSCOPE bibliographic detail HTML (div.biblio blocks).
- csir_nml / csir_immt / jnarddc / dst_serb: saved project-listing HTML
  (div.project cards with link + date + description).
- openalex: saved OpenAlex /works API response JSON.
"""
import json
import re

from .base import (
    REQUIRED_PATENT,
    REQUIRED_PUBLICATION,
    REQUIRED_RD,
    BaseAdapter,
    clean_text,
)

_IPC = re.compile(r"[A-Z]\d{2}[A-Z]?\d+/\d+")


def _first_text(items):
    items = items or []
    return clean_text(items[0].get("text")) if items else ""


class GooglePatentsAdapter(BaseAdapter):
    source_id = "google_patents"
    kind = "patent"
    required = REQUIRED_PATENT

    def parse(self, raw):
        records = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            pub_no = clean_text(row.get("publication_number"))
            records.append(
                {
                    "source_id": self.source_id,
                    "kind": self.kind,
                    "source_url": f"https://patents.google.com/patent/{pub_no}",
                    "appl_no": pub_no,
                    "title": _first_text(row.get("title_localized")),
                    "abstract": _first_text(row.get("abstract_localized")),
                    "applicants": [a.get("name") for a in row.get("assignee", [])],
                    "inventors": [i.get("name") for i in row.get("inventor", [])],
                    "ipc_codes": [c.get("code") for c in row.get("ipc", []) if c.get("code")],
                    "filing_date": str(row.get("filing_date") or ""),
                    "legal_status": "Published"
                    if str(pub_no).endswith("A")
                    else clean_text(row.get("legal_status")),
                }
            )
        return records


_BIBLIO = re.compile(r'<div class="biblio" data-docid="([^"]+)">(.*?)</div>\s*(?=<div|\Z)', re.S)


def _span(block, cls):
    m = re.search(rf'<span class="{cls}">(.*?)</span>', block, re.S)
    return clean_text(m.group(1)) if m else ""


class PatentscopeAdapter(BaseAdapter):
    source_id = "patentscope"
    kind = "patent"
    required = REQUIRED_PATENT

    def parse(self, raw):
        records = []
        for docid, block in _BIBLIO.findall(raw):
            records.append(
                {
                    "source_id": self.source_id,
                    "kind": self.kind,
                    "source_url": f"https://patentscope.wipo.int/search/en/detail.jsf?docId={docid}",
                    "appl_no": docid,
                    "title": _span(block, "title"),
                    "abstract": _span(block, "abstract"),
                    "applicants": [_span(block, "applicant")],
                    "inventors": [_span(block, "inventor")],
                    "ipc_codes": [c for c in [_span(block, "ipc")] if _IPC.match(c)],
                    "filing_date": _span(block, "filing-date"),
                    "legal_status": _span(block, "status"),
                }
            )
        return records


_CARD = re.compile(
    r'<div class="project">\s*<a href="([^"]+)">(.*?)</a>\s*'
    r'<span class="date">(.*?)</span>\s*<p class="desc">(.*?)</p>\s*</div>',
    re.S,
)


class _ListingAdapter(BaseAdapter):
    kind = "rd"
    required = REQUIRED_RD

    def parse(self, raw):
        return [
            {
                "source_id": self.source_id,
                "kind": self.kind,
                "source_url": clean_text(url),
                "title": clean_text(title),
                "abstract": clean_text(desc),
                "filing_date": clean_text(date),
            }
            for url, title, date, desc in _CARD.findall(raw)
        ]


class CsirNmlAdapter(_ListingAdapter):
    source_id = "csir_nml"


class CsirImmtAdapter(_ListingAdapter):
    source_id = "csir_immt"


class JnarddcAdapter(_ListingAdapter):
    source_id = "jnarddc"


class DstSerbAdapter(_ListingAdapter):
    source_id = "dst_serb"


class OpenAlexAdapter(BaseAdapter):
    source_id = "openalex"
    kind = "publication"
    required = REQUIRED_PUBLICATION

    def parse(self, raw):
        records = []
        for w in json.loads(raw).get("results", []):
            loc = w.get("primary_location") or {}
            orgs = []
            for a in w.get("authorships", []):
                orgs += [i.get("display_name") for i in a.get("institutions", [])]
            records.append(
                {
                    "source_id": self.source_id,
                    "kind": self.kind,
                    "source_url": clean_text(loc.get("landing_page_url") or w.get("id")),
                    "title": clean_text(w.get("title")),
                    "abstract": clean_text(w.get("abstract")),
                    "applicants": orgs,
                    "filing_date": clean_text(w.get("publication_date")),
                }
            )
        return records


ADAPTERS = [
    GooglePatentsAdapter(),
    PatentscopeAdapter(),
    CsirNmlAdapter(),
    CsirImmtAdapter(),
    JnarddcAdapter(),
    DstSerbAdapter(),
    OpenAlexAdapter(),
]


def get_adapter(source_id):
    for a in ADAPTERS:
        if a.source_id == source_id:
            return a
    raise KeyError(f"unknown source: {source_id}")
