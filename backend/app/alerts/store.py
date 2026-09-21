"""Subscription store with seen-state dedupe (Stage 5). Stdlib only.

Semantics: check() evaluates candidate records against all subscriptions;
a record fires at most once ever (seen keys persist). A repeated harvest of
the same records therefore fires zero alerts — the s5 gate property.
Subscriptions match on exact mineral/stage/kind facets + optional query
tokens (subset match over title+abstract, same tokenizer spirit as search).
"""
import json
import pathlib
import re

_TOKEN = re.compile(r"[a-z0-9]+")


class AlertStore:
    def __init__(self, path):
        self.path = pathlib.Path(path)
        if self.path.exists():
            data = json.loads(self.path.read_text())
            self.subs = data.get("subscriptions", [])
            self.seen = set(data.get("seen", []))
        else:
            self.subs, self.seen = [], set()

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"subscriptions": self.subs,
                                         "seen": sorted(self.seen)}, indent=2))

    def subscribe(self, mineral=None, stage=None, kind=None, q=""):
        sub = {"id": f"sub-{len(self.subs) + 1:03d}", "mineral": mineral,
               "stage": stage, "kind": kind, "q": q or ""}
        self.subs.append(sub)
        self._save()
        return sub

    @staticmethod
    def _matches(sub, rec):
        if sub["mineral"] and sub["mineral"] not in rec.get("mineral_ids", []):
            return False
        if sub["stage"] and sub["stage"] not in rec.get("stage_ids", []):
            return False
        if sub["kind"] and sub["kind"] != rec.get("kind"):
            return False
        if sub["q"]:
            hay = _TOKEN.findall(f"{rec.get('title', '')} {rec.get('abstract', '')}".lower())
            if not set(_TOKEN.findall(sub["q"].lower())) <= set(hay):
                return False
        return True

    def check(self, records):
        fired = []
        for r in records:
            key = r.get("doc_id") or r.get("source_url")
            if key in self.seen:
                continue
            self.seen.add(key)
            for sub in self.subs:
                if self._matches(sub, r):
                    fired.append({"sub_id": sub["id"], "record_id": key,
                                  "title": r.get("title", "")})
        self._save()
        return fired
