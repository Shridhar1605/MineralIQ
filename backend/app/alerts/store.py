"""Subscription store with per-subscription seen-state (Stage 5). Stdlib only.

Semantics: a record fires at most once *per subscription*. Seen keys are held
on the subscription, not globally, so a repeated harvest of the same records
fires zero alerts (the s5 gate property) while a subscription created later
still receives everything that arrives after it.

A new subscription is seeded with the keys already in the corpus, so
subscribing does not replay history as a flood of alerts. "Notify me of new
patents" means new, not "everything ever harvested".

The previous global seen-set marked every record as seen on first check
regardless of whether anything matched, so any subscription created after the
first /alerts/check was permanently deaf to records already in the store.

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
            legacy = set(data.get("seen", []))
        else:
            self.subs, legacy = [], set()
        # Migrate stores written under the old global-seen scheme: fold the
        # shared set into each existing subscription so nothing re-fires.
        for sub in self.subs:
            sub["seen"] = sorted(set(sub.get("seen", [])) | legacy)

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"subscriptions": self.subs}, indent=2))

    @staticmethod
    def record_key(rec):
        return rec.get("doc_id") or rec.get("source_url")

    def subscribe(self, mineral=None, stage=None, kind=None, q="", known_records=None):
        """Create a subscription.

        `known_records` is the corpus as it stands now. Those keys are marked
        seen, so the subscriber is alerted about what arrives next rather than
        about everything already harvested.
        """
        sub = {"id": f"sub-{len(self.subs) + 1:03d}", "mineral": mineral,
               "stage": stage, "kind": kind, "q": q or "",
               "seen": sorted({self.record_key(r) for r in (known_records or [])
                               if self.record_key(r)})}
        self.subs.append(sub)
        self._save()
        return {k: v for k, v in sub.items() if k != "seen"}

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
        """Fire each unseen record at every subscription it matches.

        Seen-state is per subscription, so one subscriber consuming a record
        never silences it for another, and a record is marked seen only on the
        subscriptions that were actually offered it.
        """
        fired = []
        for sub in self.subs:
            seen = set(sub.get("seen", []))
            for r in records:
                key = self.record_key(r)
                if not key or key in seen:
                    continue
                seen.add(key)
                if self._matches(sub, r):
                    fired.append({"sub_id": sub["id"], "record_id": key,
                                  "title": r.get("title", "")})
            sub["seen"] = sorted(seen)
        self._save()
        return fired
