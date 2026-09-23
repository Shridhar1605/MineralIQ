"""Harvest the Indian Patent Office Official Journal (primary patent source).

Pipeline per journal part:  listing page -> PDF (cached) -> pdftotext ->
parse every application record -> keep candidates -> data/raw_ipo.jsonl.

Every parsed record of every part is archived under data/ipo_parsed/, so the
candidate rule can be changed later and re-applied without downloading
anything again.

Compliance (plan Section 4; guidelines Sections 11 and 15), enforced in code:
  * FileName values are only ever taken from the listing page; any other value
    is refused before a request is made (see ingest/ipo_journal.py).
  * One download at a time, --pause seconds between requests (default 10),
    identified User-Agent, and a PDF already in the cache is never re-fetched.
  * No login, no CAPTCHA, no session tricks: the same POST a browser sends.

Requires pdftotext (poppler):  brew install poppler | apt-get install poppler-utils

Usage:
  python3 scripts/harvest_ipo.py --latest 1          # newest journal
  python3 scripts/harvest_ipo.py --latest 4
  python3 scripts/harvest_ipo.py --since 2024        # every journal from 2024
  python3 scripts/harvest_ipo.py --journals 38/2026,37/2026
  python3 scripts/harvest_ipo.py --latest 52 --plan  # show what would be fetched
"""
import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "app"))

from ingest.base import today  # noqa: E402
from ingest.ipo_journal import (LISTING_URL, VIEW_URL, allowed_file_names,  # noqa: E402
                                list_journals, parse_journal_text)

DATA = ROOT / "data"
CACHE = DATA / "ipo_cache"
PARSED = DATA / "ipo_parsed"
OUT = DATA / "raw_ipo.jsonl"
UA = "MineralIQ-CMiH2026/0.1 (academic hackathon prototype; public Official Journal)"

# Recall-oriented candidate rule. Precision is the classifier's job downstream;
# anything dropped here is only recoverable by re-running over the archive.
KEYWORDS = re.compile(
    r"lithium|spodumene|lepidolite|petalite|rare[ -]earth|neodymium|praseodymium|"
    r"dysprosium|terbium|lanthanum|cerium|samarium|monazite|graphite|graphene|"
    r"cobalt|nickel|laterite|critical mineral|beneficiation|hydrometallurg|"
    r"pyrometallurg|solvent extraction|leaching|black mass|flotation", re.I)
IPC_PREFIXES = ("C22B", "C01D", "C01F", "C01G", "C01B 32", "H01M", "H01F 1",
                "B03B", "B03C", "B03D", "C25C", "C22C")


# Parts I and II carry the published applications. Part III is the weekly
# list of First Examination Reports issued, Part IV is designs; skipping them
# saves a download per week and is gentler on the server.
APPLICATION_PART = re.compile(r"^part\s*(i|ii|1|2)\b(?!.*design)", re.I)


def candidate_reason(rec):
    text = f"{rec.get('title', '')} {rec.get('abstract', '')}"
    kws = sorted({m.group(0).lower() for m in KEYWORDS.finditer(text)})
    ipcs = sorted({p for p in IPC_PREFIXES for c in rec.get("ipc_codes", []) if c.startswith(p)})
    if not kws and not ipcs:
        return None
    return {"keywords": kws, "ipc": ipcs}


def fetch(url, data=None, timeout=900):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def slug(journal_no, label):
    return f"{journal_no.replace('/', '-')}_{re.sub(r'[^A-Za-z0-9]+', '-', label).strip('-')}"


def select(journals, args):
    if args.journals:
        wanted = {j.strip() for j in args.journals.split(",")}
        return [j for j in journals if j["journal_no"] in wanted]
    if args.since:
        return [j for j in journals if int(j["journal_no"].split("/")[1]) >= args.since]
    return journals[: args.latest]


def download_part(part, allowed, pause):
    """POST the page-provided FileName. Refuses anything the page did not offer."""
    fn = part["file_name"]
    if fn not in allowed:
        raise PermissionError(f"refusing FileName not offered by the listing page: {fn!r}")
    body = urllib.parse.urlencode({"FileName": fn}).encode()
    data = fetch(VIEW_URL, data=body)
    time.sleep(pause)
    if not data.startswith(b"%PDF"):
        raise RuntimeError(f"not a PDF ({len(data)} bytes) for {fn!r}")
    return data


def pdf_to_text(pdf_path):
    if not shutil.which("pdftotext"):
        sys.exit("pdftotext not found: brew install poppler  (or apt-get install poppler-utils)")
    txt = pdf_path.with_suffix(".txt")
    if not txt.exists():
        subprocess.run(["pdftotext", str(pdf_path), str(txt)], check=True)
    return txt.read_text(encoding="utf-8", errors="replace")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--latest", type=int, default=1)
    g.add_argument("--since", type=int, help="first year to include, e.g. 2024")
    g.add_argument("--journals", help="comma list, e.g. 38/2026,37/2026")
    ap.add_argument("--all-parts", action="store_true",
                    help="also fetch Part III (weekly FER lists) and Part IV (designs); "
                         "neither contains application records")
    ap.add_argument("--pause", type=float, default=10.0, help="seconds between downloads")
    ap.add_argument("--plan", action="store_true", help="list what would be fetched, fetch nothing")
    args = ap.parse_args()

    for d in (CACHE, PARSED):
        d.mkdir(parents=True, exist_ok=True)

    listing = fetch(LISTING_URL).decode("utf-8", "replace")
    (CACHE / f"listing_{today()}.html").write_text(listing)
    journals = list_journals(listing)
    allowed = allowed_file_names(journals)
    chosen = select(journals, args)
    print(f"listing: {len(journals)} journals, newest {journals[0]['journal_no']}; "
          f"selected {len(chosen)}")

    todo = []
    for j in chosen:
        for part in j["parts"]:
            if not args.all_parts and not APPLICATION_PART.search(part["label"]):
                continue
            todo.append((j, part))
    cached = sum(1 for j, p in todo if (CACHE / f"{slug(j['journal_no'], p['label'])}.pdf").exists())
    print(f"parts: {len(todo)} ({cached} already cached, {len(todo) - cached} to download)")
    if args.plan:
        for j, p in todo:
            print(f"  {j['journal_no']:8s} {j['published']}  {p['label']}")
        return 0

    existing = set()
    if OUT.exists():
        existing = {json.loads(l)["source_url"] for l in OUT.open() if l.strip()}
    total = kept = 0
    with OUT.open("a") as out:
        for j, part in todo:
            name = slug(j["journal_no"], part["label"])
            pdf = CACHE / f"{name}.pdf"
            if not pdf.exists():
                print(f"  downloading {j['journal_no']} {part['label']} ...", flush=True)
                pdf.write_bytes(download_part(part, allowed, args.pause))
            recs = parse_journal_text(pdf_to_text(pdf), j["journal_no"], part["label"])
            fetched = today()
            with (PARSED / f"{name}.jsonl").open("w") as arch:
                for r in recs:
                    r["fetched_at"] = fetched
                    arch.write(json.dumps(r, ensure_ascii=False) + "\n")
            n_keep = 0
            for r in recs:
                why = candidate_reason(r)
                if not why or r["source_url"] in existing:
                    continue
                r["candidate_reason"] = why
                out.write(json.dumps(r, ensure_ascii=False) + "\n")
                existing.add(r["source_url"])
                n_keep += 1
            total += len(recs)
            kept += n_keep
            print(f"  {j['journal_no']:8s} {part['label']:24s} records={len(recs):5d} candidates={n_keep}")
    print(f"TOTAL records parsed={total} new candidates={kept} -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
