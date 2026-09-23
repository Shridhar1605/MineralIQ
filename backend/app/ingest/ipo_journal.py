"""Indian Patent Office Official Journal: listing and record parsing.

Source: https://search.ipindia.gov.in/IPOJournal/Journal/Patent — the weekly
Official Journal of the Patent Office, a public government publication. The
listing page and the PDF downloads need no login and no CAPTCHA, and neither
ipindia host restricts crawling in robots.txt (checked 2026-09-23).

Compliance rules this module enforces (plan Section 4, guidelines Sections 11
and 15):

* Downloads replay the exact form the listing page renders: a POST to
  /IPOJournal/Journal/ViewJournal with the hidden FileName value *read from the
  page*. ``list_journals`` is the only producer of FileName values, and the
  harvester refuses any value it did not get from there. FileName is a server
  path; constructing or editing one to reach other files would be unauthorised
  access, which the guidelines treat as grounds for disqualification.
* One download at a time with a pause between, identified User-Agent, PDFs
  cached locally so no journal is ever fetched twice.

Record format (pdftotext reading order): WIPO INID-coded fields, e.g.
(21) application number, (22) filing date, (43) publication date,
(54) title, (51) IPC, (71) applicants, (72) inventors, (57) abstract.
The IPC column is interleaved line by line with the applicant column in the
extracted text, so IPC codes are reassembled from subclass and group tokens
rather than read as one field.
"""
import html
import re

LISTING_URL = "https://search.ipindia.gov.in/IPOJournal/Journal/Patent"
VIEW_URL = "https://search.ipindia.gov.in/IPOJournal/Journal/ViewJournal"
SOURCE_ID = "ipo_journal"

# --------------------------------------------------------------------------- #
# listing page
# --------------------------------------------------------------------------- #
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_FORM = re.compile(
    r'<form[^>]*action="/IPOJournal/Journal/ViewJournal"[^>]*>.*?'
    r'name="FileName"\s+value="([^"]+)".*?<button[^>]*>(.*?)</button>',
    re.S | re.I)


def _text(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def list_journals(listing_html):
    """Parse the public listing into journals and their downloadable parts.

    Returns [{"journal_no": "38/2026", "published": "18/09/2026",
              "parts": [{"label": "Part I", "file_name": "<exact page value>"}]}]
    """
    out = []
    for row in _ROW.findall(listing_html):
        cells = _CELL.findall(row)
        if len(cells) < 5:
            continue
        journal_no, published = _text(cells[1]), _text(cells[2])
        if not re.fullmatch(r"\d{1,2}/\d{4}", journal_no):
            continue
        parts = [{"label": _text(label), "file_name": html.unescape(fn)}
                 for fn, label in _FORM.findall(cells[4])]
        out.append({"journal_no": journal_no, "published": published, "parts": parts})
    return out


def allowed_file_names(journals):
    """Every FileName the page offered. The harvester may submit only these."""
    return {p["file_name"] for j in journals for p in j["parts"]}


# --------------------------------------------------------------------------- #
# record parsing
# --------------------------------------------------------------------------- #
_FOOTER = re.compile(
    r"The Patent Office Journal No\.\s*\d+/\d{4}\s+Dated\s+\d{2}/\d{2}/\d{4}\s*\d*")
_SPLIT = re.compile(r"\(12\)\s*PATENT APPLICATION PUBLICATION")
_APPL = re.compile(r"\(21\)\s*Application No\.?\s*([0-9]{8,})\s*([A-Z])?")
_FILED = re.compile(r"\(22\)\s*Date of filing of Application\s*:\s*(\d{2}/\d{2}/\d{4})")
_PUBD = re.compile(r"\(43\)\s*Publication Date\s*:\s*(\d{2}/\d{2}/\d{4})")
_TITLE = re.compile(r"\(54\)\s*Title of the invention\s*:\s*(.+?)(?:\n\s*\n|\(51\))", re.S)
_ABSTRACT = re.compile(r"\(57\)\s*Abstract\s*:\s*(.+?)(?:No\.\s*of\s*Pages\s*:|\Z)", re.S)
_PAGES = re.compile(r"No\.\s*of\s*Pages\s*:\s*(\d+)\s*No\.\s*of\s*Claims\s*:\s*(\d+)")

_SUBCLASS = re.compile(r"^:?([A-H]\d{2}[A-Z])$")
# compact form, subclass and group in one token: "B09B3/00", ":F01K23/06"
_COMPACT = re.compile(r"^:?([A-H]\d{2}[A-Z])(\d{1,4}/\d{2,6})$")
_GROUP = re.compile(r"^(\d{1,4}/\d{2,6})$")
# fixed-width long form: 4-char subclass, 4-digit group, 6-digit subgroup,
# e.g. "C12Q0001700000" = C12Q 1/70, "A61K0031443900" = A61K 31/4439
_LONG = re.compile(r"^:?([A-H]\d{2}[A-Z])(\d{4})(\d{6})$")


def _decode_long(sub, group, subgroup):
    g = str(int(group))
    sg = subgroup.rstrip("0").ljust(2, "0")
    return f"{sub} {g}/{sg}"
_INLINE_IPC = re.compile(r"([A-H]\d{2}[A-Z])\s+(\d{1,4}/\d{2,6})")
# "1)Name" anywhere on a line: the extracted text often puts an IPC fragment
# or a priority-field value in front of it ("F01K23/06, 1)RAVI KUMAR",
# ":01/01/1900 2)Jyoti Sehrawat").
_NAME = re.compile(r"(?:^|[\s,:])(\d{1,2})\)\s*(\S.*?)\s*$")


def _clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def _iso(d):
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", d or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def _ipc_codes(block):
    """Reassemble IPC codes whose subclass and group landed on separate lines."""
    codes, pending = [], None
    for raw in re.split(r"[\s,]+", block):
        tok = raw.strip()
        if not tok:
            continue
        long_form = _LONG.match(tok)
        if long_form:
            if pending:
                codes.append(pending)
                pending = None
            codes.append(_decode_long(*long_form.groups()))
            continue
        compact = _COMPACT.match(tok)
        if compact:
            if pending:
                codes.append(pending)
                pending = None
            codes.append(f"{compact.group(1)} {compact.group(2)}")
            continue
        sub = _SUBCLASS.match(tok)
        if sub:
            if pending:
                codes.append(pending)
            pending = sub.group(1)
            continue
        grp = _GROUP.match(tok)
        if grp and pending:
            codes.append(f"{pending} {grp.group(1)}")
            pending = None
    if pending:
        codes.append(pending)
    # codes written on one line ("B09B 3/00") are caught by the token walk
    # above only when split; add any inline ones it missed
    for sub, grp in _INLINE_IPC.findall(block):
        code = f"{sub} {grp}"
        if code not in codes:
            codes.append(code)
    seen, out = set(), []
    for c in codes:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _is_ipc_fragment(line):
    s = line.strip().rstrip(",")
    return bool(_SUBCLASS.match(s) or _GROUP.match(s) or re.fullmatch(
        r"([A-H]\d{2}[A-Z]\s+\d{1,4}/\d{2,6},?\s*)+", s))


def _names(section):
    names = []
    for line in section.splitlines():
        if _is_ipc_fragment(line) or line.strip().startswith("Address of"):
            continue
        m = _NAME.search(line)
        if m:
            name = _clean(m.group(2))
            if name and name not in names:
                names.append(name)
    return names


def parse_record(block, journal_no="", part_label=""):
    """One '(12) PATENT APPLICATION PUBLICATION' block -> canonical record."""
    appl = _APPL.search(block)
    if not appl:
        return None
    appl_no = appl.group(1)
    kind = appl.group(2) or "A"

    head = block.split("(57)", 1)[0]
    ipc_region = head.split("(51)", 1)[1] if "(51)" in head else ""
    applicants_section, inventors_section = "", ""
    if "(71)" in head:
        after71 = head.split("(71)", 1)[1]
        if "(72)" in after71:
            applicants_section, inventors_section = after71.split("(72)", 1)
        else:
            applicants_section = after71

    title = _TITLE.search(block)
    abstract = _ABSTRACT.search(block)
    pages = _PAGES.search(block)
    anchor = f"{journal_no}/{part_label}/{appl_no}".replace(" ", "-")
    return {
        "source_id": SOURCE_ID,
        "kind": "patent",
        "source_url": f"{LISTING_URL}#{anchor}",
        "appl_no": appl_no,
        "kind_code": kind,
        "title": _clean(title.group(1)) if title else "",
        "abstract": _clean(abstract.group(1)) if abstract else "",
        "applicants": _names(applicants_section),
        "inventors": _names(inventors_section),
        "ipc_codes": _ipc_codes(ipc_region),
        "filing_date": _iso((_FILED.search(block) or [None, ""])[1]),
        "publication_date": _iso((_PUBD.search(block) or [None, ""])[1]),
        "journal_no": journal_no,
        "journal_part": part_label,
        "pages": int(pages.group(1)) if pages else None,
        "claims": int(pages.group(2)) if pages else None,
        "legal_status": "Published",
    }


def parse_journal_text(text, journal_no="", part_label=""):
    """Full pdftotext output of one journal part -> list of records."""
    text = _FOOTER.sub("", text)
    out = []
    for block in _SPLIT.split(text)[1:]:
        rec = parse_record(block, journal_no, part_label)
        if rec:
            out.append(rec)
    return out
