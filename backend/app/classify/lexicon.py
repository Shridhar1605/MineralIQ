"""Lexicon baseline classifier (Stage 3). Stdlib only, runs offline in batch —
the web server never loads a model (plan §Stage 3, keeps the 8 GB machine viable).

Design rules (anti-gaming):
- Mineral terms come ONLY from taxonomy_v1.json (lexicon + symbols + members).
- Stage/family keywords are generic process vocabulary defined below, NOT
  derived from hold-out texts. The frozen hold-out is evaluation-only.
- Short terms (<=3 chars: Li, Co, Ni, Nd, sx, hpal, ...) match whole-word only;
  longer terms match as substrings. This avoids 'ni' matching 'nickel'-style
  accidents in reverse ('C' matching every 'carbon' is still a known
  limitation — documented, and why Week 2 fine-tunes a real model).
- A process family is predicted only if its parent stage is also predicted.
"""
import json
import pathlib
import re

# (whole-word terms, substring terms) per value-chain stage.
STAGE_KEYWORDS = {
    "exploration": (
        ["mapping", "targeting", "drilling", "assay", "survey"],
        ["prospect", "remote sensing", "sentinel", "aeromag", "radiomet",
         "hyperspectral", "geophys", "geochem"],
    ),
    "mining": (
        ["mining", "mine", "mines", "pit", "pits"],
        ["underground", "stoping", "backfill", "evaporation"],
    ),
    "beneficiation": (
        [],
        ["beneficiation", "flotation", "crushing", "grinding", "comminution",
         "magnetic separation", "gravity separation", "dense media"],
    ),
    "extraction_refining": (
        ["hpal", "sx", "dle", "resin"],
        ["extraction", "leach", "hydrometallurg", "pyrometallurg", "roast",
         "smelt", "calcin", "solvent extraction", "ion exchange",
         "ion-exchange", "adsorb", "electrowinning", "precipitat",
         "crystalli", "bioleach"],
    ),
    "materials": (
        ["lfp", "nmc", "nca"],
        ["cathode", "anode", "magnet", "ndfeb", "alloy", "electrolyte",
         "spheronis", "spheroniz"],
    ),
    "recycling": (
        ["scrap"],
        ["recycl", "black mass", "spent"],
    ),
}

# family_id -> (whole-word terms, substring terms). Parent stage gate applies.
FAMILY_KEYWORDS = {
    "remote_sensing": ([], ["remote sensing", "sentinel", "spectral"]),
    "geophysics": ([], ["aeromag", "radiomet", "electromagnetic"]),
    "geochemistry": ([], ["geochem", "assay"]),
    "solution_mining": (["sweep"], ["brine pumping", "evaporation pond", "dle"]),
    "flotation": ([], ["flotation"]),
    "crushing_grinding": ([], ["crushing", "grinding", "comminution"]),
    "hydrometallurgy": (["hpal"], ["hydrometallurg", "leach", "bioleach"]),
    "pyrometallurgy": ([], ["pyrometallurg", "roast", "smelt", "calcin"]),
    "solvent_extraction": (["sx"], ["solvent extraction", "extractant"]),
    "ion_exchange": (["dle", "resin"], ["ion exchange", "ion-exchange", "adsorb"]),
    "electrowinning": ([], ["electrowinning", "precipitat", "crystalli"]),
    "cathode": (["lfp", "nmc", "nca"], ["cathode"]),
    "anode": ([], ["anode", "spheronis", "spheroniz"]),
    "magnet": ([], ["magnet", "ndfeb"]),
    "mech_recycling": ([], ["dismantling", "shredding", "black mass"]),
    "hydro_recycling": ([], ["black mass", "battery_sx"]),
    "direct_recycling": ([], ["direct recycling", "cathode_healing", "cathode healing"]),
}


def _word_hit(term, text):
    return re.search(rf"\b{re.escape(term)}\b", text) is not None


class LexiconClassifier:
    def __init__(self, taxonomy_path):
        tax = json.loads(pathlib.Path(taxonomy_path).read_text())
        self.minerals = {}  # mineral_id -> (word_terms, sub_terms)
        for m in tax["minerals"]:
            words, subs = set(), set()
            for t in m.get("lexicon", []):
                (words if len(t) <= 3 else subs).add(t.lower())
            for t in m.get("symbols", []) + m.get("members", []):
                words.add(t.lower())
            self.minerals[m["id"]] = (words, subs)
        self.stages = {s["id"] for s in tax["value_chain_stages"]}
        self.family_stage = {f["id"]: f["stage"] for f in tax["process_families"]}

    @staticmethod
    def _any(words, subs, text):
        return any(_word_hit(w, text) for w in words) or any(s in text for s in subs)

    def predict(self, title, abstract=""):
        text = f"{title or ''} {abstract or ''}".lower()
        minerals = sorted(
            mid for mid, (w, s) in self.minerals.items() if self._any(w, s, text)
        )
        stages = sorted(
            sid
            for sid in self.stages
            if sid in STAGE_KEYWORDS and self._any(*STAGE_KEYWORDS[sid], text)
        )
        families = sorted(
            fid
            for fid, kw in FAMILY_KEYWORDS.items()
            if self.family_stage.get(fid) in stages and self._any(*kw, text)
        )
        return {"mineral_ids": minerals, "stage_ids": stages,
                "process_family_ids": families}
