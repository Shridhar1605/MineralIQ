"""Stage 1 volume check for replacement patent sources: EPO OPS and Lens.org.

Why this exists: the Google Patents BigQuery spike showed that a count can
mislead. That dataset holds 83,504 Indian records but only 238 have a title,
so "records exist" said nothing about "records are usable". This probe
therefore reports two things per source:

  1. how many Indian publications match each pilot mineral, and
  2. for a small sample, whether the title and abstract are actually present.

A source passes only if both look healthy.

Credentials live OUTSIDE the repository, mode 600, and are never printed:

  ~/.config/mineraliq/epo_ops.json   {"key": "...", "secret": "..."}
  ~/.config/mineraliq/lens_token     one line, the Lens access token

Compliance (plan Section 4): authenticated API access only, no scraping,
requests spaced out and backed off on throttling responses.

Usage:
  python3 scripts/source_probe.py            # both sources
  python3 scripts/source_probe.py --only ops
  python3 scripts/source_probe.py --only lens
"""
import argparse
import base64
import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

CONF = pathlib.Path.home() / ".config" / "mineraliq"
OPS_CREDS = CONF / "epo_ops.json"
LENS_TOKEN = CONF / "lens_token"

OPS_BASE = "https://ops.epo.org/3.2"
LENS_SEARCH = "https://api.lens.org/patent/search"

PILOT = {
    "LI": ["lithium", "spodumene", "lepidolite"],
    "REE": ["neodymium", "praseodymium", "dysprosium", "monazite", "lanthanum"],
    "GRA": ["graphite", "graphene"],
    "CO": ["cobalt"],
    "NI": ["nickel", "laterite"],
}
SINCE_YEAR = 2010
PAUSE_S = 2.5          # stays well under per-minute search limits
UA = "MineralIQ-CMiH2026/0.1 (academic hackathon prototype)"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _request(url, data=None, headers=None, method=None, retries=3):
    """HTTP with polite backoff. Returns (status, headers, body_text)."""
    hdrs = {"User-Agent": UA, **(headers or {})}
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code in (429, 503) and attempt < retries - 1:
                wait = int(e.headers.get("Retry-After", "0") or 0) or 15 * (attempt + 1)
                print(f"    throttled ({e.code}), waiting {wait}s")
                time.sleep(wait)
                continue
            return e.code, dict(e.headers), body
    return 0, {}, "retries exhausted"


def _sample_quality(samples):
    """Fraction of sampled records that carry a non-empty title and abstract."""
    if not samples:
        return 0.0, 0.0
    t = sum(1 for s in samples if (s.get("title") or "").strip()) / len(samples)
    a = sum(1 for s in samples if (s.get("abstract") or "").strip()) / len(samples)
    return t, a


# --------------------------------------------------------------------------- #
# EPO Open Patent Services
# --------------------------------------------------------------------------- #
def ops_token():
    creds = json.loads(OPS_CREDS.read_text())
    basic = base64.b64encode(f"{creds['key']}:{creds['secret']}".encode()).decode()
    status, _, body = _request(
        f"{OPS_BASE}/auth/accesstoken",
        data=b"grant_type=client_credentials",
        headers={"Authorization": f"Basic {basic}",
                 "Content-Type": "application/x-www-form-urlencoded"},
        method="POST")
    if status != 200:
        raise RuntimeError(f"OPS auth failed [{status}]: {body[:200]}")
    return json.loads(body)["access_token"]


def ops_search(token, cql, constituent="", rng="1-1"):
    path = "/rest-services/published-data/search" + (f"/{constituent}" if constituent else "")
    url = f"{OPS_BASE}{path}?" + urllib.parse.urlencode({"q": cql, "Range": rng})
    status, headers, body = _request(url, headers={"Authorization": f"Bearer {token}",
                                                   "Accept": "application/json"})
    throttle = headers.get("X-Throttling-Control") or headers.get("x-throttling-control")
    time.sleep(PAUSE_S)
    return status, body, throttle


def _ops_total(body):
    d = json.loads(body)
    return int(d["ops:world-patent-data"]["ops:biblio-search"]["@total-result-count"])


def _ops_text(node):
    if isinstance(node, list):
        en = [n for n in node if isinstance(n, dict) and n.get("@lang") == "en"]
        node = (en or node)[0] if (en or node) else {}
    if isinstance(node, dict):
        if "$" in node:
            return node["$"]
        if "p" in node:
            return _ops_text(node["p"])
    return ""


def probe_ops():
    print("\n=== EPO Open Patent Services ===")
    if not OPS_CREDS.exists():
        print(f"  no credentials at {OPS_CREDS}; skipping")
        return None
    token = ops_token()
    print("  authenticated")
    date = f'pd within "{SINCE_YEAR} 2026"'
    counts = {}
    status, body, throttle = ops_search(token, f"pn=IN and {date}")
    if status != 200:
        print(f"  search failed [{status}]: {body[:240]}")
        return None
    counts["ALL_IN"] = _ops_total(body)
    print(f"  Indian publications {SINCE_YEAR}+ : {counts['ALL_IN']:,}")
    if throttle:
        print(f"  throttling header            : {throttle}")
    for mineral, terms in PILOT.items():
        cql = f'pn=IN and {date} and ta any "{" ".join(terms)}"'
        status, body, _ = ops_search(token, cql)
        counts[mineral] = _ops_total(body) if status == 200 else f"error {status}"
        shown = f"{counts[mineral]:,}" if isinstance(counts[mineral], int) else counts[mineral]
        print(f"  {mineral:4s} title/abstract matches  : {shown}")

    # Is the content real, or stubs? Pull a small biblio sample.
    cql = f'pn=IN and {date} and ta any "{" ".join(PILOT["LI"] + PILOT["REE"])}"'
    status, body, _ = ops_search(token, cql, constituent="biblio", rng="1-10")
    samples = []
    if status == 200:
        docs = json.loads(body)["ops:world-patent-data"]["ops:biblio-search"]["ops:search-result"]
        docs = docs.get("exchange-documents", [])
        docs = docs if isinstance(docs, list) else [docs]
        for d in docs:
            ex = d.get("exchange-document", {})
            bib = ex.get("bibliographic-data", {})
            samples.append({"id": f"{ex.get('@country','')}{ex.get('@doc-number','')}{ex.get('@kind','')}",
                            "title": _ops_text(bib.get("invention-title", {})),
                            "abstract": _ops_text(ex.get("abstract", {}))})
    t, a = _sample_quality(samples)
    print(f"  sample of {len(samples)}: {t:.0%} have a title, {a:.0%} have an abstract")
    for s in samples[:4]:
        print(f"    {s['id']:18s} {s['title'][:70]}")
    return {"source": "epo_ops", "counts": counts, "sample_title": t, "sample_abstract": a}


# --------------------------------------------------------------------------- #
# Lens.org
# --------------------------------------------------------------------------- #
def lens_search(token, query_string, size=0, include=None):
    body = {"query": {"query_string": {"query": query_string}}, "size": size}
    if include:
        body["include"] = include
    status, headers, text = _request(
        LENS_SEARCH, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST")
    remaining = {k: v for k, v in headers.items() if k.lower().startswith("x-rate-limit")}
    time.sleep(PAUSE_S)
    return status, text, remaining


def probe_lens():
    print("\n=== Lens.org ===")
    if not LENS_TOKEN.exists():
        print(f"  no token at {LENS_TOKEN}; skipping")
        return None
    token = LENS_TOKEN.read_text().strip()
    base = f"jurisdiction:IN AND year_published:[{SINCE_YEAR} TO 2026]"
    counts = {}
    status, text, remaining = lens_search(token, base)
    if status != 200:
        print(f"  search failed [{status}]: {text[:240]}")
        return None
    counts["ALL_IN"] = json.loads(text).get("total", 0)
    print(f"  Indian publications {SINCE_YEAR}+ : {counts['ALL_IN']:,}")
    if remaining:
        print(f"  rate-limit headers           : {remaining}")
    for mineral, terms in PILOT.items():
        ors = " OR ".join(terms)
        q = f"{base} AND (title:({ors}) OR abstract:({ors}))"
        status, text, _ = lens_search(token, q)
        counts[mineral] = json.loads(text).get("total", 0) if status == 200 else f"error {status}"
        shown = f"{counts[mineral]:,}" if isinstance(counts[mineral], int) else counts[mineral]
        print(f"  {mineral:4s} title/abstract matches  : {shown}")

    ors = " OR ".join(PILOT["LI"] + PILOT["REE"])
    q = f"{base} AND (title:({ors}) OR abstract:({ors}))"
    status, text, _ = lens_search(token, q, size=10,
                                  include=["lens_id", "doc_number", "kind",
                                           "biblio.invention_title", "abstract"])
    samples = []
    if status == 200:
        for d in json.loads(text).get("data", []):
            titles = (d.get("biblio") or {}).get("invention_title") or []
            abstracts = d.get("abstract") or []
            pick = lambda xs: next((x.get("text", "") for x in xs if x.get("lang") == "en"),
                                   xs[0].get("text", "") if xs else "")
            samples.append({"id": f"IN{d.get('doc_number','')}{d.get('kind','')}",
                            "title": pick(titles), "abstract": pick(abstracts)})
    t, a = _sample_quality(samples)
    print(f"  sample of {len(samples)}: {t:.0%} have a title, {a:.0%} have an abstract")
    for s in samples[:4]:
        print(f"    {s['id']:18s} {s['title'][:70]}")
    return {"source": "lens", "counts": counts, "sample_title": t, "sample_abstract": a}


# --------------------------------------------------------------------------- #
def verdict(result):
    """Pass only if the volume is there AND the sampled content is real."""
    if not result:
        return "NOT RUN"
    c = result["counts"]
    pilot = sum(v for k, v in c.items() if k != "ALL_IN" and isinstance(v, int))
    ok_volume = pilot >= 2000
    ok_content = result["sample_title"] >= 0.8 and result["sample_abstract"] >= 0.6
    return (f"{'PASS' if ok_volume and ok_content else 'FAIL'} "
            f"(pilot matches {pilot:,} vs 2,000 target, overlaps counted per mineral; "
            f"titles {result['sample_title']:.0%}, abstracts {result['sample_abstract']:.0%})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["ops", "lens"])
    args = ap.parse_args()
    results = {}
    if args.only in (None, "ops"):
        results["ops"] = probe_ops()
    if args.only in (None, "lens"):
        results["lens"] = probe_lens()
    print("\n=== Verdict (Stage 1 volume check) ===")
    for name, r in results.items():
        print(f"  {name:5s} {verdict(r)}")
    print(json.dumps({k: v for k, v in results.items() if v}, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
