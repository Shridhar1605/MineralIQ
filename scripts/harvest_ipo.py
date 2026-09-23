"""Harvest the Indian Patent Office Official Journal (primary patent source).

Pipeline per journal part:  listing page -> PDF (cached) -> pdftotext ->
parse every application record -> keep candidates -> data/raw_ipo.jsonl.

Every parsed record of every part is archived under data/ipo_parsed/, so the
candidate rule can be changed later and re-applied without downloading
anything again.

Compliance (plan Section 4; guidelines Sections 11 and 15), enforced in code:
  * FileName values are only ever taken from the listing page; any other value
    is refused before a request is made (see ingest/ipo_journal.py).
  * At most --workers downloads in flight (default 4, hard cap 6) and at least
    --pause seconds between request starts across all workers (default 1 s).
    Each part is one request that streams for about a minute, so this is a few
    requests per minute, well inside the <=1 request/second commitment in the
    idea submission. The server's own transfer speed is the bottleneck.
  * On HTTP 429/5xx or a network error the harvester backs off exponentially
    and doubles the gap between requests for the rest of the run.
  * A PDF already in the cache is never re-fetched; downloads are written to a
    temp file and renamed, so an interrupted run never leaves a truncated PDF
    that later passes as cached.
  * No login, no CAPTCHA, no session tricks: the same POST a browser sends.

Requires pdftotext (poppler):  brew install poppler | apt-get install poppler-utils

Usage:
  python3 scripts/harvest_ipo.py --latest 1          # newest journal
  python3 scripts/harvest_ipo.py --latest 4
  python3 scripts/harvest_ipo.py --since 2024        # every journal from 2024
  python3 scripts/harvest_ipo.py --journals 38/2026,37/2026
  python3 scripts/harvest_ipo.py --latest 52 --plan  # show what would be fetched
  python3 scripts/harvest_ipo.py --since 2025 --workers 4
"""
import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

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


MAX_WORKERS = 6


class RateGate:
    """Minimum spacing between request *starts*, shared by every worker.
    `slow_down()` doubles the spacing when the server pushes back."""

    def __init__(self, interval):
        self.interval = interval
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self):
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next)
            self._next = start + self.interval
        time.sleep(max(0.0, start - now))

    def slow_down(self):
        with self._lock:
            self.interval = min(max(self.interval * 2, 2.0), 60.0)
            return self.interval


def download_part(part, allowed, pause=0.0, gate=None, retries=4, log=print):
    """POST the page-provided FileName. Refuses anything the page did not offer."""
    fn = part["file_name"]
    if fn not in allowed:
        raise PermissionError(f"refusing FileName not offered by the listing page: {fn!r}")
    body = urllib.parse.urlencode({"FileName": fn}).encode()
    for attempt in range(retries):
        if gate:
            gate.wait()
        try:
            data = fetch(VIEW_URL, data=body)
            if not data.startswith(b"%PDF"):
                raise RuntimeError(f"not a PDF ({len(data)} bytes)")
            if pause:
                time.sleep(pause)
            return data
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == retries - 1:
                raise
            reason = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError, RuntimeError) as e:
            if attempt == retries - 1:
                raise
            reason = type(e).__name__
        wait = 30 * 2 ** attempt
        spacing = gate.slow_down() if gate else None
        log(f"    {part['label']}: {reason}, retry {attempt + 1} in {wait}s"
            + (f", request gap now {spacing:.0f}s" if spacing else ""))
        time.sleep(wait)
    raise RuntimeError("unreachable")


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
    ap.add_argument("--pause", type=float, default=1.0,
                    help="minimum seconds between request starts, all workers combined")
    ap.add_argument("--workers", type=int, default=4,
                    help=f"parallel downloads (hard cap {MAX_WORKERS})")
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

    workers = max(1, min(args.workers, MAX_WORKERS))
    if workers != args.workers:
        print(f"workers capped at {MAX_WORKERS}")
    gate = RateGate(args.pause)
    lock = threading.Lock()

    def log(msg):
        with lock:
            print(msg, flush=True)

    def fetch_and_extract(j, part):
        """Worker: download if not cached (atomic), then pdftotext."""
        name = slug(j["journal_no"], part["label"])
        pdf = CACHE / f"{name}.pdf"
        if not pdf.exists():
            t0 = time.monotonic()
            data = download_part(part, allowed, gate=gate, log=log)
            tmp = pdf.with_suffix(".pdf.part")
            tmp.write_bytes(data)
            tmp.replace(pdf)
            secs = time.monotonic() - t0
            log(f"  got {j['journal_no']:8s} {part['label']:8s} "
                f"{len(data) / 1e6:5.1f} MB in {secs:4.0f}s")
        return j, part, pdf_to_text(pdf)

    existing = set()
    if OUT.exists():
        existing = {json.loads(l)["source_url"] for l in OUT.open() if l.strip()}
    total = kept = 0
    failed = []
    t_start = time.monotonic()
    with OUT.open("a") as out, ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_and_extract, j, p): (j, p) for j, p in todo}
        for done, fut in enumerate(as_completed(futures), 1):
            j, part = futures[fut]
            try:
                _, _, text = fut.result()
            except Exception as e:  # noqa: BLE001 - report and keep going
                failed.append((j["journal_no"], part["label"], f"{type(e).__name__}: {e}"))
                log(f"  FAILED {j['journal_no']} {part['label']}: {e}")
                continue
            name = slug(j["journal_no"], part["label"])
            recs = parse_journal_text(text, j["journal_no"], part["label"])
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
            out.flush()
            total += len(recs)
            kept += n_keep
            mins = (time.monotonic() - t_start) / 60
            log(f"  [{done:3d}/{len(todo)}] {j['journal_no']:8s} {part['label']:8s} "
                f"records={len(recs):5d} candidates={n_keep:3d}  ({mins:5.1f} min)")
    if failed:
        print(f"\n{len(failed)} part(s) failed; re-run the same command to retry them:")
        for f in failed:
            print("  ", *f)
    print(f"TOTAL records parsed={total} new candidates={kept} -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
