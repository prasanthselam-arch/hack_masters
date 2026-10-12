"""Deterministic medical knowledge: lab catalog, drug dictionary, dosage terms, ICD-10.

Everything here is pure code + curated data so validation never depends on the LLM.
"""

import csv
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process

KDIR = Path(__file__).parent


def _clean(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[\(\)\[\],:;*#]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip(" .-")


# ---------------------------------------------------------------- units

_UNIT_SUBS: list[tuple[str, str]] = [
    (r"[µμ]", "u"),
    (r"mcg", "ug"),
    (r"\s+", ""),
    (r"cells?/", "/"),
    (r"(cu\.?mm|c\.?mm|cmm|mm\^?3|mm³|microl(itre|iter)?|mcl)", "ul"),
    (r"x?10\^?\s*3|x?10³|10e3|thou(sand)?s?|th/", "10^3"),
    (r"x?10\^?\s*6|x?10⁶|10e6|millions?|mill?\.?", "10^6"),
    (r"x?10\^?\s*9|x?10⁹|10e9", "10^9"),
    (r"x?10\^?\s*12|x?10¹²|10e12", "10^12"),
    (r"lakhs?|lacs?", "lakh"),
    (r"^gms?", "g"),
    (r"^g(m)?%$", "g/dl"),
    (r"^mg%$", "mg/dl"),
    (r"hours?|hrs?", "h"),
    (r"beats/min|bpm|/minute", "/min"),
    (r"breaths/min", "/min"),
    (r"°f|degf|deg\.?f|^f$", "degf"),
    (r"°c|degc|deg\.?c|^c$", "degc"),
    (r"mmofhg", "mmhg"),
    (r"miu/l|mu/l|uu/ml", "uiu/ml"),
    (r"1\.73m\^?2|1\.73m²", "1.73m2"),
    (r"kg/m\^?2|kg/m²", "kg/m2"),
]


def norm_unit(unit: str | None) -> str:
    if not unit:
        return ""
    u = unit.strip().lower()
    for pat, rep in _UNIT_SUBS:
        u = re.sub(pat, rep, u)
    u = u.replace("10^3/l", "10^3/ul") if u.endswith("10^3/l") and "10^3" in u else u
    if u in ("10^3", "k"):
        u = "10^3/ul"
    if u.startswith("k/"):
        u = "10^3/" + u[2:]
    if u in ("lakh", "lakh/ul"):
        u = "lakh/ul"
    if u in ("10^6", "10^6/ul"):
        u = "10^6/ul"
    if u in ("/ul", "ul", "/"):
        u = "/ul"
    return u


# ---------------------------------------------------------------- lab catalog

@dataclass
class LabTest:
    key: str
    loinc: str
    display: str
    panel: str
    category: str
    aliases: list[str]
    unit: str
    conversions: dict[str, Any]  # normalized unit -> factor | {a, b}
    ranges: dict[str, list[float | None]]
    plausible: list[float]
    critical: list[float | None] | None
    what: str
    low: str
    high: str

    def convert(self, value: float, unit: str | None) -> tuple[float, bool] | None:
        """Return (value in canonical unit, was_converted) or None if the unit is unknown."""
        nu = norm_unit(unit)
        if nu == "" or nu == norm_unit(self.unit):
            return value, False
        conv = self.conversions.get(nu)
        if conv is None:
            return None
        if isinstance(conv, dict):
            return conv["a"] * value + conv["b"], True
        return value * conv, conv != 1

    def ref_range(self, sex: str | None) -> tuple[float | None, float | None]:
        if sex in ("male", "female") and sex in self.ranges:
            lo, hi = self.ranges[sex]
        elif "any" in self.ranges:
            lo, hi = self.ranges["any"]
        else:
            # sex unknown but sex-specific: use the widest span to avoid false alarms
            lows = [r[0] for r in self.ranges.values() if r[0] is not None]
            highs = [r[1] for r in self.ranges.values() if r[1] is not None]
            lo = min(lows) if lows else None
            hi = max(highs) if highs else None
        return lo, hi


class LabCatalog:
    def __init__(self) -> None:
        data = json.loads((KDIR / "lab_ranges.json").read_text())
        self.tests: dict[str, LabTest] = {}
        self._alias: dict[str, str] = {}
        for t in data["tests"]:
            conv = {norm_unit(k): v for k, v in t["conversions"].items()}
            lt = LabTest(
                key=t["key"], loinc=t["loinc"], display=t["display"], panel=t["panel"],
                category=t["category"], aliases=t["aliases"], unit=t["unit"], conversions=conv,
                ranges=t["ranges"], plausible=t["plausible"], critical=t.get("critical"),
                what=t.get("what", ""), low=t.get("low", ""), high=t.get("high", ""),
            )
            self.tests[lt.key] = lt
            for a in [lt.display, *lt.aliases]:
                self._alias.setdefault(_clean(a), lt.key)
        self._fuzzy_keys = [a for a in self._alias if len(a) > 4]
        self.by_loinc = {t.loinc: t for t in self.tests.values()}

    def match(self, *names: str | None, panel: str | None = None) -> tuple[LabTest | None, float]:
        cands = [_clean(n) for n in names if n]
        for c in cands:
            for variant in (c, re.sub(r"^(serum|s|blood|plasma)\.? ", "", c)):
                if variant in self._alias:
                    return self.tests[self._alias[variant]], 1.0
        best: tuple[LabTest | None, float] = (None, 0.0)
        for c in cands:
            if len(c) <= 4:
                continue
            hit = process.extractOne(c, self._fuzzy_keys, scorer=fuzz.token_sort_ratio, score_cutoff=88)
            if hit and hit[1] / 100 > best[1]:
                best = (self.tests[self._alias[hit[0]]], hit[1] / 100)
        return best


# ---------------------------------------------------------------- drugs

@dataclass
class Drug:
    brand: str
    generic: str
    drug_class: str
    forms: list[str]
    strengths: list[str]
    common_use: str


_FORM_WORDS = r"\b(tab|tabs|tablet|tablets|cap|caps|capsule|capsules|syp|syr|syrup|inj|injection|susp|suspension|oint|ointment|cream|gel|drops?|inhaler|sachet|t\.|c\.)\b\.?"


def _clean_drug(name: str) -> str:
    s = name.lower()
    s = re.sub(_FORM_WORDS, " ", s)
    s = re.sub(r"\d+(\.\d+)?\s*(mg|mcg|g|ml|iu|%)\b", " ", s)
    s = re.sub(r"[^a-z0-9\+ ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


class DrugDictionary:
    def __init__(self) -> None:
        self.drugs: list[Drug] = []
        with open(KDIR / "drugs_india.csv", newline="") as f:
            for row in csv.DictReader(f):
                self.drugs.append(Drug(
                    brand=row["brand"], generic=row["generic"], drug_class=row["drug_class"],
                    forms=[x for x in row["forms"].split("|") if x],
                    strengths=[x for x in row["strengths"].split("|") if x],
                    common_use=row["common_use"],
                ))
        self._names: dict[str, int] = {}
        for i, d in enumerate(self.drugs):
            self._names.setdefault(_clean_drug(d.brand), i)
            self._names.setdefault(_clean_drug(d.generic), i)
        self._keys = list(self._names)

    def match(self, *names: str | None) -> tuple[Drug | None, float, str | None]:
        best: tuple[Drug | None, float, str | None] = (None, 0.0, None)
        for n in names:
            if not n:
                continue
            c = _clean_drug(n)
            if not c:
                continue
            if c in self._names:
                return self.drugs[self._names[c]], 1.0, c
            # brand plus suffix such as "dolo 650" or "telma 40" -> strip trailing digits
            c2 = re.sub(r"\s+\d+$", "", c)
            if c2 in self._names:
                return self.drugs[self._names[c2]], 0.98, c2
            hit = process.extractOne(c, self._keys, scorer=fuzz.WRatio, score_cutoff=85)
            if hit and hit[1] / 100 > best[1]:
                best = (self.drugs[self._names[hit[0]]], hit[1] / 100, hit[0])
        return best


# ---------------------------------------------------------------- dosage terms

class DosageTerms:
    def __init__(self) -> None:
        d = json.loads((KDIR / "dosage_terms.json").read_text())
        self.freq = d["frequencies"]
        self.meal = d["meal_relation"]
        self.tod = d["time_of_day"]
        self.routes = d["routes"]
        self._freq_alias = {a: code for code, v in self.freq.items() for a in v["aliases"]}

    def parse_frequency(self, text: str | None) -> dict[str, Any]:
        """Parse '1-0-1', 'BD', '1/2-0-1', 'सुबह-शाम' etc. into a normalized schedule."""
        out: dict[str, Any] = {"code": None, "morning": None, "afternoon": None, "night": None, "text": None}
        if not text:
            return out
        t = text.strip().lower()
        num = r"(\d+(?:\.\d+)?|½|1/2|¼|1/4|¾)"
        m = re.search(rf"{num}\s*[-–—x×]\s*{num}\s*[-–—x×]\s*{num}(?:\s*[-–—x×]\s*{num})?", t)
        if m:
            vals = [self._num(g) for g in m.groups() if g is not None]
            if len(vals) == 4:  # morning-noon-evening-night
                morning, afternoon, night = vals[0], vals[1], vals[2] + vals[3]
            else:
                morning, afternoon, night = vals
            out.update(morning=morning, afternoon=afternoon, night=night, code="CUSTOM")
            per_day = sum(1 for v in (morning, afternoon, night) if v)
            pattern = tuple(1 if v else 0 for v in (morning, afternoon, night))
            for code, v in self.freq.items():
                if v["pattern"] and tuple(v["pattern"]) == pattern and v["per_day"] == per_day:
                    out["code"] = code
                    break
            if pattern == (0, 0, 1):
                out["code"] = "HS"
            out["text"] = self._schedule_text(morning, afternoon, night)
            return out
        tokens = re.sub(r"[^\w\s\./]", " ", t)
        for alias in sorted(self._freq_alias, key=len, reverse=True):
            if re.search(rf"(?<![\w]){re.escape(alias)}(?![\w])", tokens):
                code = self._freq_alias[alias]
                f = self.freq[code]
                out["code"] = code
                out["text"] = f["text"]
                if f["pattern"]:
                    out["morning"], out["afternoon"], out["night"] = (float(x) for x in f["pattern"])
                return out
        # regional-language time-of-day words, e.g. "सुबह-शाम" -> morning + night
        hits = {slot: any(w in t for w in words) for slot, words in self.tod.items()}
        if any(hits.values()):
            m_, a_, n_ = (1.0 if hits[s] else 0.0 for s in ("morning", "afternoon", "night"))
            out.update(morning=m_, afternoon=a_, night=n_, code="CUSTOM", text=self._schedule_text(m_, a_, n_))
            pattern = (int(m_), int(a_), int(n_))
            for code, v in self.freq.items():
                if v["pattern"] and tuple(v["pattern"]) == pattern:
                    out["code"] = code
        return out

    def parse_meal(self, *texts: str | None) -> str | None:
        joined = " ".join(t.lower() for t in texts if t)
        if not joined:
            return None
        for rel, words in self.meal.items():
            for w in sorted(words, key=len, reverse=True):
                if len(w) <= 3:
                    if re.search(rf"(?<![\w]){re.escape(w)}(?![\w])", joined):
                        return rel
                elif w in joined:
                    return rel
        return None

    def parse_route(self, *texts: str | None) -> str | None:
        joined = " ".join(t.lower() for t in texts if t)
        for route, words in self.routes.items():
            if any(re.search(rf"(?<![\w]){re.escape(w)}(?![\w])", joined) for w in words):
                return route
        return None

    @staticmethod
    def parse_duration_days(text: str | None) -> int | None:
        if not text:
            return None
        t = text.lower().replace("×", "x")
        m = re.search(r"(\d+)\s*/\s*7\b", t)
        if m:
            return int(m.group(1))
        m = re.search(r"(\d+)\s*/\s*52\b", t)
        if m:
            return int(m.group(1)) * 7
        m = re.search(r"(\d+(?:\.\d+)?)\s*(d|day|days|दिन|రోజులు|రోజు|நாட்கள்|நாள்|ದಿನ|ದಿನಗಳು)\b", t)
        if m:
            return int(float(m.group(1)))
        m = re.search(r"(\d+(?:\.\d+)?)\s*(w|wk|wks|week|weeks|सप्ताह|हफ्ते|వారాలు|வாரம்|ವಾರ)\b", t)
        if m:
            return int(float(m.group(1)) * 7)
        m = re.search(r"(\d+(?:\.\d+)?)\s*(m|mo|mon|month|months|महीने|महीना|నెల|மாதம்|ತಿಂಗಳು)\b", t)
        if m:
            return int(float(m.group(1)) * 30)
        m = re.search(r"\b(one|a)\s+(week|month)\b", t)
        if m:
            return 7 if m.group(2) == "week" else 30
        return None

    @staticmethod
    def _num(s: str) -> float:
        return {"½": 0.5, "1/2": 0.5, "¼": 0.25, "1/4": 0.25, "¾": 0.75}.get(s, None) or float(s)

    @staticmethod
    def _schedule_text(m: float | None, a: float | None, n: float | None) -> str:
        parts = []
        for v, label in ((m, "morning"), (a, "afternoon"), (n, "night")):
            if v:
                parts.append(f"{v:g} in the {label}" if label != "night" else f"{v:g} at night")
        return ", ".join(parts) if parts else "as directed"


# ---------------------------------------------------------------- ICD-10

class Icd10Map:
    def __init__(self) -> None:
        d = json.loads((KDIR / "icd10.json").read_text())
        self.items = d["conditions"]
        self._alias: dict[str, int] = {}
        for i, c in enumerate(self.items):
            for a in [c["display"], *c["aliases"]]:
                self._alias.setdefault(_clean(a), i)
        self._fuzzy = [a for a in self._alias if len(a) > 4]
        self.by_code = {c["code"]: c for c in self.items}

    def match(self, *names: str | None) -> tuple[dict | None, float]:
        best: tuple[dict | None, float] = (None, 0.0)
        for n in names:
            if not n:
                continue
            c = _clean(n)
            c = re.sub(r"^(k/c/o|kco|known case of|h/o|c/o|known)\s+", "", c)
            if c in self._alias:
                return self.items[self._alias[c]], 1.0
            if len(c) <= 4:
                continue
            hit = process.extractOne(c, self._fuzzy, scorer=fuzz.token_sort_ratio, score_cutoff=90)
            if hit and hit[1] / 100 > best[1]:
                best = (self.items[self._alias[hit[0]]], hit[1] / 100)
        return best


@lru_cache
def labs() -> LabCatalog:
    return LabCatalog()


@lru_cache
def drugs() -> DrugDictionary:
    return DrugDictionary()


@lru_cache
def dosage() -> DosageTerms:
    return DosageTerms()


@lru_cache
def icd10() -> Icd10Map:
    return Icd10Map()
