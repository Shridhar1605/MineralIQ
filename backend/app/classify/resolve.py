"""Organisation name resolution (Stage 3). Explicit alias-map merging only.

Anti-merger-collision rule: 'Council of Scientific and Industrial Research'
(CSIR HQ, cf. golden PAT-LI-001) and 'CSIR-NML' (the Jamshedpur laboratory,
cf. golden PAT-REE-001) resolve to DIFFERENT canonicals. Merging happens only
through fixtures/org_aliases.json — never by fuzzy heuristics — so there are
no silent wrong merges. Unknown names become their own normalized node.
"""
import json
import pathlib
import re

_PUNCT = re.compile(r"[.,()\"'&/\\-]")


def normalize(name):
    name = (name or "").lower()
    name = _PUNCT.sub(" ", name)
    return re.sub(r"\s+", " ", name).strip()


class OrgResolver:
    def __init__(self, aliases_path):
        data = json.loads(pathlib.Path(aliases_path).read_text())
        self.index = {}
        for canonical, variants in data["aliases"].items():
            self.index[normalize(canonical)] = canonical
            for v in variants:
                key = normalize(v)
                if key in self.index and self.index[key] != canonical:
                    raise ValueError(f"variant collision: {v!r} maps twice")
                self.index[key] = canonical
        self.top = list(data.get("top20", []))

    def resolve(self, name):
        return self.index.get(normalize(name), normalize(name) or "unknown")

    def merge_report(self):
        """Variant -> canonical for every listed alias (the 90% gate input)."""
        data = self.index
        return dict(data)
