"""Deterministic validation + normalization of an extraction into a ReviewPayload.

Nothing here calls an LLM. Abnormal/critical flags are computed in code so the
summary model can only explain them, never decide them.
"""

import re
from collections.abc import Callable
from datetime import date, timedelta

from dateutil import parser as dateparser
from rapidfuzz import fuzz

from app.knowledge import _clean, _clean_drug, dosage, drugs, icd10, labs, norm_unit
from app.schemas.extraction import (
    Classification,
    DocumentExtraction,
    ExtractedMedication,
    ExtractedTest,
    VerificationResult,
)
from app.schemas.review import (
    Issue,
    ReviewCondition,
    ReviewDocument,
    ReviewEncounter,
    ReviewMedication,
    ReviewObservation,
    ReviewPatient,
    ReviewPayload,
    ReviewStats,
)

REVIEW_THRESHOLD = 0.85
_NUM = re.compile(r"^\s*([<>≤≥]=?|<=|>=)?\s*([-+]?\d[\d,]*(?:\.\d+)?)\s*$")
# a number followed only by a printed flag and/or unit: "12.5 L", "12.5 g/dL", "142 (H)", "6.8*"
_NUM_TAIL = re.compile(r"^\s*([<>≤≥]=?|<=|>=)?\s*([-+]?\d[\d,]*(?:\.\d+)?)\s*(?:\(?\s*(?:hh|ll|h|l|high|low|\*+)\s*\)?)?\s*([a-zµ%][\w/%^.µ]*)?\s*$", re.I)
_BAND = re.compile(r"([a-z][a-z \-/()]*?)\s*[:=]?\s*((?:<=|>=|≤|≥|<|>|up\s*to|upto|less than|below|more than|above|greater than)?\s*[-+]?\d+(?:\.\d+)?(?:\s*-\s*[-+]?\d+(?:\.\d+)?)?)")
_NORMAL_BAND = re.compile(r"\b(normal|desirable|optimal|non[- ]?diabetic|sufficient|reference|healthy|adults?)\b")
_SEX_BAND = {"female": re.compile(r"\b(female|women|f)\b"), "male": re.compile(r"\b(male|men|m)\b")}
_POSITIVE = ("positive", "reactive", "detected", "present", "+ve", "seen")
_NEGATIVE = ("negative", "non-reactive", "non reactive", "not detected", "absent", "nil", "-ve", "not seen")


# ------------------------------------------------------------------ helpers

def _ev(v) -> str:
    return getattr(v, "value", v)


def parse_number(text: str | None) -> tuple[float | None, str | None]:
    """'1,50,000' -> 150000; '<0.5' -> (0.5, '<'); 'Positive' -> (None, None)."""
    if text is None:
        return None, None
    m = _NUM.match(str(text).replace(" ", "")) or _NUM_TAIL.match(str(text))
    if not m:
        return None, None
    try:
        return float(m.group(2).replace(",", "")), m.group(1)
    except ValueError:
        return None, None


def _range_text_norm(text: str) -> str:
    t = text.lower().replace(",", "").replace("–", "-").replace("—", "-")
    return re.sub(r"(\d)\s+to\s+(\d)", r"\1-\2", t)


def range_bands(text: str | None) -> list[tuple[str, str]]:
    """Labelled bands such as 'Desirable <200 Borderline 200-239' or 'Male 13-17 Female 12-15'."""
    if not text:
        return []
    return [(label.strip(), expr) for label, expr in _BAND.findall(_range_text_norm(text)) if re.search(r"[a-z]{3,}|\b[mf]\b", label)]


def parse_range(text: str | None, sex: str | None = None) -> tuple[float | None, float | None]:
    if not text:
        return None, None
    bands = range_bands(text)
    if len(bands) >= 2:
        # several bands: use the patient's sex, else the normal/desirable band; otherwise it is ambiguous
        pick = next((e for lbl, e in bands if sex in _SEX_BAND and _SEX_BAND[sex].search(lbl)), None) \
            or next((e for lbl, e in bands if _NORMAL_BAND.search(lbl)), None)
        return _parse_range_expr(pick) if pick else (None, None)
    return _parse_range_expr(_range_text_norm(text))


def _parse_range_expr(t: str) -> tuple[float | None, float | None]:
    m = re.search(r"([-+]?\d+(?:\.\d+)?)\s*-\s*([-+]?\d+(?:\.\d+)?)", t)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return (lo, hi) if lo <= hi else (hi, lo)
    m = re.search(r"(<=|≤|<|up\s*to|upto|less than|below)\s*([-+]?\d+(?:\.\d+)?)", t)
    if m:
        return None, float(m.group(2))
    m = re.search(r"(>=|≥|>|more than|above|greater than)\s*([-+]?\d+(?:\.\d+)?)", t)
    if m:
        return float(m.group(2)), None
    return None, None


def parse_date(iso: str | None, as_written: str | None, issues: list[Issue], path: str) -> str | None:
    """Prefer re-parsing the verbatim text (day-first) and cross-check the model's ISO date."""
    parsed_written: date | None = None
    if as_written:
        try:
            year_first = bool(re.match(r"\s*\d{4}[/.\-]", as_written))  # 2026-03-02 is ISO, not DD-MM
            parsed_written = dateparser.parse(as_written, dayfirst=not year_first, yearfirst=year_first, fuzzy=True, default=None).date()  # type: ignore[union-attr]
        except (ValueError, OverflowError, AttributeError, TypeError):
            parsed_written = None
    parsed_iso: date | None = None
    if iso:
        try:
            parsed_iso = date.fromisoformat(iso[:10])
        except ValueError:
            issues.append(Issue(level="warning", code="date_format", message=f"Unrecognised date '{iso}'", path=path))
    chosen = parsed_iso or parsed_written
    if parsed_iso and parsed_written and parsed_iso != parsed_written:
        if parsed_written.year > 1900 and as_written and re.search(r"\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}", as_written):
            chosen = parsed_written
            issues.append(Issue(level="warning", code="date_mismatch",
                                message=f"Date '{as_written}' read as {parsed_written.isoformat()} (DD/MM); model said {parsed_iso.isoformat()}",
                                path=path))
    if chosen is None:
        return None
    today = date.today()
    if chosen > today + timedelta(days=1):
        issues.append(Issue(level="error", code="future_date", message=f"Date {chosen.isoformat()} is in the future; please check", path=path))
    elif chosen.year < 1950:
        issues.append(Issue(level="warning", code="old_date", message=f"Date {chosen.isoformat()} looks too old; please check", path=path))
    return chosen.isoformat()


def _norm_strength(s: str | None) -> str:
    if not s:
        return ""
    s = s.lower().replace("mcg", "ug").replace("µg", "ug").replace(" ", "")
    return s


# ------------------------------------------------------------------ observations

def build_observations(tests: list[ExtractedTest], sex: str | None, doc_date: str | None) -> list[ReviewObservation]:
    out: list[ReviewObservation] = []
    for i, t in enumerate(_split_bp(tests)):
        out.append(_observation(t, sex, f"tests[{i}]"))
    return out


def _split_bp(tests: list[ExtractedTest]) -> list[ExtractedTest]:
    res: list[ExtractedTest] = []
    for t in tests:
        m = re.match(r"^\s*(\d{2,3})\s*/\s*(\d{2,3})\s*$", t.value_as_written or "")
        if m and ("blood pressure" in t.test_name.lower() or t.test_name.lower() in ("bp", "b.p.", "b.p")):
            for label, val in (("Systolic Blood Pressure", m.group(1)), ("Diastolic Blood Pressure", m.group(2))):
                res.append(t.model_copy(update={
                    "test_name": label, "value_as_written": val, "value_numeric": float(val),
                    "unit": t.unit or "mmHg", "reference_range_as_written": None, "ref_low": None, "ref_high": None,
                    "category": "vital-signs",
                }))
        else:
            res.append(t)
    return res


def _observation(t: ExtractedTest, sex: str | None, path: str) -> ReviewObservation:
    issues: list[Issue] = []
    entry, score = labs().match(t.test_name, t.test_name_as_written)
    conf = float(t.confidence)

    # value: trust the verbatim text over the model's numeric copy
    num, comparator = parse_number(t.value_as_written)
    if num is None and t.value_numeric is not None and not re.search(r"[a-zA-Z]", t.value_as_written or ""):
        num = float(t.value_numeric)
    if num is not None and t.value_numeric is not None and abs(num - float(t.value_numeric)) > 1e-6 * max(1, abs(num)):
        issues.append(Issue(level="warning", code="value_mismatch",
                            message=f"Numeric value {t.value_numeric} differs from printed '{t.value_as_written}'; using printed value",
                            path=f"{path}.value"))
        conf = min(conf, 0.8)

    value_text = None if (num is not None and not comparator) else t.value_as_written
    tail = _NUM_TAIL.match(t.value_as_written or "")
    unit_orig = t.unit or (tail.group(3) if tail and num is not None else None)
    ref_lo, ref_hi = parse_range(t.reference_range_as_written, sex)
    banded = len(range_bands(t.reference_range_as_written)) >= 2  # the model's copy may be the wrong band
    if ref_lo is None and ref_hi is None and (t.ref_low is not None or t.ref_high is not None) and t.reference_range_as_written and not banded:
        ref_lo, ref_hi = t.ref_low, t.ref_high
    ref_source = "report" if (ref_lo is not None or ref_hi is not None) else None

    name = t.test_name
    loinc = None
    unit = unit_orig
    value_canon = num
    interpretation: str | None = None
    critical = False
    unit_ok = True  # value (and any report range) are in the catalog's canonical unit

    if entry is not None:
        name, loinc = entry.display, entry.loinc
        if num is not None:
            conv = entry.convert(num, unit_orig)
            if conv is None:
                inferred = _infer_unit(entry, num)
                if inferred is not None:
                    value_canon, unit = inferred, entry.unit
                    issues.append(Issue(level="warning", code="unit_inferred",
                                        message=f"Unit '{unit_orig}' not recognised for {entry.display}; interpreted as {entry.unit}",
                                        path=f"{path}.unit"))
                    conf = min(conf, 0.8)
                else:
                    issues.append(Issue(level="warning", code="unit_unknown",
                                        message=f"Unit '{unit_orig}' not recognised for {entry.display}; value kept as printed",
                                        path=f"{path}.unit"))
                    value_canon, unit = num, unit_orig
                    unit_ok = False
            else:
                value_canon, converted = conv
                unit = entry.unit
                if not unit_orig:
                    issues.append(Issue(level="info", code="unit_missing",
                                        message=f"No unit printed; assumed {entry.unit}", path=f"{path}.unit"))
                if converted:
                    issues.append(Issue(level="info", code="unit_converted",
                                        message=f"Converted {t.value_as_written} {unit_orig} to {_fmt(value_canon)} {entry.unit}",
                                        path=f"{path}.unit"))
                    if ref_lo is not None:
                        ref_lo = entry.convert(ref_lo, unit_orig)[0]  # type: ignore[index]
                    if ref_hi is not None:
                        ref_hi = entry.convert(ref_hi, unit_orig)[0]  # type: ignore[index]

            plo, phi = entry.plausible
            if unit_ok and value_canon is not None and not (plo <= value_canon <= phi):
                issues.append(Issue(level="error", code="implausible",
                                    message=f"{_fmt(value_canon)} {unit} is outside the physiologically possible range for {entry.display}; likely misread",
                                    path=f"{path}.value"))
                conf = min(conf, 0.5)

        if ref_source is None and unit_ok:
            lo, hi = entry.ref_range(sex)
            if lo is not None or hi is not None:
                ref_lo, ref_hi, ref_source = lo, hi, "curated"
    elif num is not None:
        issues.append(Issue(level="info", code="test_unmapped",
                            message=f"'{t.test_name}' is not in the test catalog; flag uses the printed range only", path=path))

    if value_canon is not None and (ref_lo is not None or ref_hi is not None):
        if ref_lo is not None and value_canon < ref_lo:
            interpretation = "L"
        elif ref_hi is not None and value_canon > ref_hi:
            interpretation = "H"
        else:
            interpretation = "N"
        if comparator and (
            (comparator.startswith(("<", "≤")) and interpretation == "H") or (comparator.startswith((">", "≥")) and interpretation == "L")
        ):
            interpretation = None  # a bound-only result such as "<0.5" cannot be classified against this range
        if entry is not None and entry.critical and unit_ok:
            clo, chi = entry.critical
            if clo is not None and value_canon < clo:
                interpretation, critical = "LL", True
            elif chi is not None and value_canon > chi:
                interpretation, critical = "HH", True
    elif value_text:
        low = value_text.lower()
        if any(w in low for w in _NEGATIVE):
            interpretation = "N"
        elif any(w in low for w in _POSITIVE):
            interpretation = "A"

    if t.flag_on_report and interpretation:
        f = t.flag_on_report.strip().lower()
        rep = "H" if f.startswith(("h", "↑")) else "L" if f.startswith(("l", "↓")) else None
        mine = interpretation[0] if interpretation in ("H", "L", "HH", "LL") else interpretation
        if rep and mine != rep:
            issues.append(Issue(level="warning", code="flag_mismatch",
                                message=f"Report marks this '{t.flag_on_report}' but the value vs range reads as {interpretation}; please verify the value",
                                path=f"{path}.value"))
            conf = min(conf, 0.8)

    ref_text = t.reference_range_as_written
    if ref_source == "curated":
        ref_text = _range_text(ref_lo, ref_hi, unit) + " (standard adult range)"

    return ReviewObservation(
        category=t.category if t.category in ("laboratory", "vital-signs") else (entry.category if entry else "laboratory"),
        panel=t.panel or (entry.panel if entry else None),
        name_raw=t.test_name_as_written, name=name, loinc=loinc,
        value_original=t.value_as_written, unit_original=unit_orig,
        value_num=_round(value_canon), value_text=value_text, unit=unit,
        ref_low=_round(ref_lo), ref_high=_round(ref_hi), ref_text=ref_text, ref_source=ref_source,
        interpretation=interpretation, critical=critical, flag_on_report=t.flag_on_report,
        confidence=round(conf, 3), page=t.page, issues=issues,
        needs_review=conf < REVIEW_THRESHOLD or any(i.level == "error" for i in issues),
    )


def _infer_unit(entry, num: float) -> float | None:
    """Value printed without a recognised unit: accept only if it is plausible as the canonical unit."""
    plo, phi = entry.plausible
    return num if plo <= num <= phi else None


def _range_text(lo: float | None, hi: float | None, unit: str | None) -> str:
    u = f" {unit}" if unit else ""
    if lo is not None and hi is not None:
        return f"{_fmt(lo)} - {_fmt(hi)}{u}"
    if hi is not None:
        return f"< {_fmt(hi)}{u}" if hi % 1 else f"≤ {_fmt(hi)}{u}"
    if lo is not None:
        return f"≥ {_fmt(lo)}{u}"
    return ""


def _fmt(v: float | None) -> str:
    if v is None:
        return ""
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _round(v: float | None) -> float | None:
    return None if v is None else round(v, 3)


# ------------------------------------------------------------------ medications

def build_medications(meds: list[ExtractedMedication]) -> list[ReviewMedication]:
    return [_medication(m, f"medications[{i}]") for i, m in enumerate(meds)]


def _medication(m: ExtractedMedication, path: str) -> ReviewMedication:
    issues: list[Issue] = []
    conf = float(m.confidence)
    dd = dosage()

    drug, score, _ = drugs().match(m.name, m.name_as_written, m.generic_name)
    generic, drug_class, common_use, dict_match = m.generic_name, None, None, None
    strength = m.strength
    if drug is not None:
        dict_match = drug.brand
        generic = drug.generic
        drug_class = drug.drug_class
        common_use = drug.common_use
        if m.generic_name and _clean_drug(m.generic_name) not in _clean_drug(drug.generic) and _clean_drug(drug.generic) not in _clean_drug(m.generic_name):
            issues.append(Issue(level="warning", code="generic_mismatch",
                                message=f"Model suggested generic '{m.generic_name}', dictionary says '{drug.generic}' for {drug.brand}",
                                path=f"{path}.generic"))
        if score < 0.95:
            issues.append(Issue(level="info", code="name_fuzzy",
                                message=f"'{m.name}' matched to '{drug.brand}' ({drug.generic}) with {score:.0%} similarity",
                                path=f"{path}.name"))
            conf = min(conf, 0.9 if score >= 0.9 else 0.8)
        if not strength:
            sm = re.search(r"\b(\d+(?:\.\d+)?)\s*(mg|mcg|g|iu)?\s*$", m.name, re.I)
            if sm and drug.strengths:
                cand = f"{sm.group(1)} {(sm.group(2) or 'mg').lower()}"
                if any(_norm_strength(cand) == _norm_strength(x.split("+")[0]) for x in drug.strengths):
                    strength = cand
                    issues.append(Issue(level="info", code="strength_from_brand",
                                        message=f"Strength {cand} taken from the brand name '{m.name}'", path=f"{path}.strength"))
        if strength and drug.strengths:
            ns = _norm_strength(strength)
            known = [_norm_strength(x) for x in drug.strengths]
            if ns and not any(ns == k or ns == k.split("+")[0] or k.startswith(ns) for k in known):
                issues.append(Issue(level="warning", code="unusual_strength",
                                    message=f"{strength} is not a usual strength of {drug.brand} ({', '.join(drug.strengths)}); please verify",
                                    path=f"{path}.strength"))
                conf = min(conf, 0.75)
    else:
        issues.append(Issue(level="info" if conf >= REVIEW_THRESHOLD else "warning", code="drug_unknown",
                            message=f"'{m.name}' was not found in the drug dictionary; please verify the name",
                            path=f"{path}.name"))

    freq = dd.parse_frequency(m.frequency_as_written)
    morning, afternoon, night = m.morning, m.afternoon, m.night
    code, ftext = freq["code"], freq["text"]
    if freq["morning"] is not None:
        if (morning, afternoon, night) != (freq["morning"], freq["afternoon"], freq["night"]) and any(
            v is not None for v in (morning, afternoon, night)
        ):
            issues.append(Issue(level="info", code="schedule_recomputed",
                                message=f"Schedule recomputed from '{m.frequency_as_written}'", path=f"{path}.frequency"))
        morning, afternoon, night = freq["morning"], freq["afternoon"], freq["night"]
    elif code is None and any(v for v in (morning, afternoon, night)):
        code = "CUSTOM"
        ftext = dd._schedule_text(morning, afternoon, night)
    if code is None and not m.frequency_as_written:
        issues.append(Issue(level="warning", code="frequency_missing", message="How often to take this is not written", path=f"{path}.frequency"))

    meal = _ev(m.meal_relation) if m.meal_relation else dd.parse_meal(m.frequency_as_written, m.instructions)
    if code == "HS" and not meal:
        meal = "bedtime"
    route = m.route or dd.parse_route(m.instructions, m.form)
    if not route and (m.form or "").lower() in ("tablet", "capsule", "syrup", "suspension", "sachet"):
        route = "oral"

    duration_days = dd.parse_duration_days(m.duration_as_written)
    if duration_days is None:
        duration_days = m.duration_days
    elif m.duration_days is not None and m.duration_days != duration_days:
        issues.append(Issue(level="info", code="duration_recomputed",
                            message=f"Duration recomputed from '{m.duration_as_written}' as {duration_days} days", path=f"{path}.duration"))

    name = m.name
    sm = re.search(r"^(.*\S)\s+(\d+(?:\.\d+)?)$", name)
    if sm and strength and re.match(rf"^{re.escape(sm.group(2))}\s*(mg|mcg|g|iu)?\b", strength.strip(), re.I):
        name = sm.group(1)  # "Telma 40" + "40 mg" -> "Telma" + "40 mg"

    return ReviewMedication(
        name_raw=m.name_as_written, name=name, generic=generic, drug_class=drug_class, common_use=common_use,
        dictionary_match=dict_match, dictionary_score=round(score, 3) if drug else None,
        strength=strength, form=m.form, dose=m.dose,
        frequency_raw=m.frequency_as_written, frequency_code=code, frequency_text=ftext,
        morning=morning, afternoon=afternoon, night=night, meal_relation=meal, route=route,
        duration_text=m.duration_as_written, duration_days=duration_days, instructions=m.instructions,
        confidence=round(conf, 3), page=m.page, issues=issues,
        needs_review=conf < REVIEW_THRESHOLD or any(i.level == "error" for i in issues),
    )


# ------------------------------------------------------------------ conditions

def build_conditions(ex: DocumentExtraction) -> list[ReviewCondition]:
    out: list[ReviewCondition] = []
    seen: set[str] = set()
    for i, d in enumerate(ex.diagnoses):
        issues: list[Issue] = []
        conf = float(d.confidence)
        hit, score = icd10().match(d.name, d.text_as_written)
        code, display = d.icd10, None
        if hit:
            if d.icd10 and d.icd10.split(".")[0] != hit["code"].split(".")[0]:
                issues.append(Issue(level="info", code="icd_replaced",
                                    message=f"ICD-10 {d.icd10} replaced by curated {hit['code']} ({hit['display']})", path=f"diagnoses[{i}].icd10"))
            code, display = hit["code"], hit["display"]
        elif d.icd10:
            issues.append(Issue(level="info", code="icd_unverified",
                                message=f"ICD-10 {d.icd10} suggested by AI and not verified against the curated list", path=f"diagnoses[{i}].icd10"))
        key = (code or _clean(d.name))
        if key in seen:
            continue
        seen.add(key)
        out.append(ReviewCondition(
            name_raw=d.text_as_written, name=d.name, icd10=code, icd10_display=display,
            verification_status="provisional" if _ev(d.status) == "provisional" else "confirmed",
            confidence=round(conf, 3), page=d.page, issues=issues, needs_review=conf < REVIEW_THRESHOLD,
        ))
    return out


# ------------------------------------------------------------------ cross-pass agreement

def _med_key(name: str) -> str:
    return re.sub(r"\s+\d+k?$", "", _clean_drug(name))


def _pair(items: list, keys_of: Callable, sim_of: Callable) -> Callable:
    """Return a finder that maps a verified item to the unused first-pass item describing the same thing.

    The two passes often word names differently ("Haematocrit" vs "Hematocrit (PCV)"), so items are matched
    on catalogue codes first and fuzzy names second; each first-pass item can be claimed only once.
    """
    used: set[int] = set()
    keyed = [(set(k for k in keys_of(it) if k), it) for it in items]

    def find(keys: set[str], name: str):
        keys = {k for k in keys if k}
        for j, (ks, it) in enumerate(keyed):
            if j not in used and ks & keys:
                used.add(j)
                return it
        best, score = None, 0.0
        for j, (_, it) in enumerate(keyed):
            if j not in used and (s := sim_of(it, name)) > score:
                best, score = j, s
        if best is not None and score >= 88:
            used.add(best)
            return keyed[best][1]
        return None

    return find


def _apply_agreement(payload: ReviewPayload, first: DocumentExtraction, vr: VerificationResult) -> None:
    uncertain = " ".join(vr.uncertain_fields)

    def med_keys(m: ExtractedMedication) -> list[str]:
        d, score, _ = drugs().match(m.name)
        return [_med_key(m.name), d.generic.lower() if d and score >= 0.9 else ""]

    find_med = _pair(first.medications, med_keys, lambda m, n: fuzz.ratio(_med_key(m.name), _med_key(n)))
    for i, m in enumerate(payload.medications):
        f = find_med({_med_key(m.name), (m.generic or "").lower()}, m.name)
        if f is None:
            m.verified = "added"
            m.needs_review = True
            m.issues.append(Issue(level="warning", code="added_by_verifier", message="Found only by the verification pass; please confirm it is on the document"))
            continue
        same = (_norm_strength(f.strength) == _norm_strength(m.strength) or (not f.strength and m.dictionary_match)) and \
            (f.frequency_as_written or "").replace(" ", "") == (m.frequency_raw or "").replace(" ", "")
        _set_agreement(m, same, f"medications[{i}]", uncertain)
    first_tests = {_clean(t.test_name): t for t in first.tests}

    def test_keys(t: ExtractedTest) -> list[str]:
        lt, score = labs().match(t.test_name)
        return [_clean(t.test_name), lt.loinc if lt and score >= 0.85 else ""]

    find_test = _pair(first.tests, test_keys, lambda t, n: fuzz.token_set_ratio(_clean(t.test_name), _clean(n)))
    for i, o in enumerate(payload.observations):
        f = find_test({_clean(o.name_raw), _clean(o.name), o.loinc or ""}, o.name_raw)
        if f is None:
            if o.category == "vital-signs" and "blood pressure" in o.name.lower():
                o.verified = "agreed" if any("blood pressure" in k or k == "bp" for k in first_tests) else "added"
            else:
                o.verified = "added"
            if o.verified == "added":
                o.needs_review = True
                o.issues.append(Issue(level="warning", code="added_by_verifier", message="Found only by the verification pass; please confirm"))
            continue
        same = (f.value_as_written or "").replace(" ", "") == (o.value_original or "").replace(" ", "") and \
            norm_unit(f.unit) == norm_unit(o.unit_original)
        _set_agreement(o, same, f"tests[{i}]", uncertain)
    def dx_keys(d) -> list[str]:
        entry, score = icd10().match(d.name)
        return [_clean(d.name), (d.icd10 or "")[:3], entry["code"][:3] if entry and score >= 0.9 else ""]

    find_dx = _pair(first.diagnoses, dx_keys, lambda d, n: fuzz.token_set_ratio(_clean(d.name), _clean(n)))
    for i, c in enumerate(payload.conditions):
        agreed = find_dx({_clean(c.name), (c.icd10 or "")[:3]}, c.name) is not None
        _set_agreement(c, agreed, f"diagnoses[{i}]", uncertain)


def _set_agreement(item, agreed: bool, path: str, uncertain: str) -> None:
    if agreed:
        item.verified = "agreed"
        item.confidence = round(1 - (1 - item.confidence) * 0.5, 3)
    else:
        item.verified = "corrected"
        item.confidence = round(min(item.confidence, 0.8), 3)
        item.issues.append(Issue(level="warning", code="passes_disagree",
                                 message="The two independent reads disagreed; the verified value is shown, please confirm"))
    if path in uncertain:
        item.confidence = round(min(item.confidence, 0.7), 3)
        item.issues.append(Issue(level="warning", code="verifier_uncertain", message="The verifier marked this as still uncertain"))
    item.needs_review = item.confidence < REVIEW_THRESHOLD or any(i.level == "error" for i in item.issues)


# ------------------------------------------------------------------ entry points

def suspicious_paths(ex: DocumentExtraction, sex: str | None) -> list[str]:
    """Quick validation pass whose findings are fed to the verifier as re-read hints."""
    payload = build_review(ex, None, sex)
    hints: list[str] = []
    for kind, items in (("medications", payload.medications), ("tests", payload.observations), ("diagnoses", payload.conditions)):
        for i, it in enumerate(items):
            for iss in it.issues:
                if iss.level in ("warning", "error"):
                    hints.append(f"{kind}[{i}] ({getattr(it, 'name', '')}): {iss.message}")
            if it.confidence < 0.7:
                hints.append(f"{kind}[{i}] ({getattr(it, 'name', '')}): low confidence {it.confidence}")
    for iss in payload.issues:
        if iss.level != "info":
            hints.append(f"{iss.path}: {iss.message}")
    return hints


def build_review(
    ex: DocumentExtraction,
    cls: Classification | None,
    sex: str | None,
    first: DocumentExtraction | None = None,
    verification: VerificationResult | None = None,
) -> ReviewPayload:
    issues: list[Issue] = []
    doc_date = parse_date(ex.document_date, ex.document_date_as_written, issues, "document_date")
    gender = (ex.patient.gender or "").lower() or None
    gender = {"m": "male", "f": "female"}.get(gender, gender) if gender else None
    sex = sex or (gender if gender in ("male", "female") else None)

    enc = None
    if ex.encounter:
        e = ex.encounter
        enc = ReviewEncounter(
            start_date=parse_date(e.admission_date, None, issues, "encounter.admission_date"),
            end_date=parse_date(e.discharge_date, None, issues, "encounter.discharge_date"),
            reason=e.reason_for_admission, hospital_course=e.hospital_course,
            procedures=e.procedures, discharge_condition=e.discharge_condition,
        )
        if enc.start_date and enc.end_date and enc.start_date > enc.end_date:
            issues.append(Issue(level="error", code="date_order", message="Admission date is after discharge date", path="encounter"))

    document = ReviewDocument(
        doc_type=_ev(ex.document_type),
        title=cls.title if cls else None,
        document_date=doc_date, document_date_raw=ex.document_date_as_written,
        facility=ex.facility_name, author=ex.doctor_name, author_registration=ex.doctor_registration,
        patient=ReviewPatient(name=ex.patient.name, age=ex.patient.age, gender=gender,
                              patient_identifier=ex.patient.patient_identifier, abha_number=ex.patient.abha_number),
        findings=ex.findings, impression=ex.impression, advice=ex.advice, follow_up=ex.follow_up,
        legibility=_ev(ex.legibility), unreadable=ex.unreadable,
        languages=cls.languages if cls else [], handwritten=cls.handwritten if cls else False,
    )
    if not doc_date:
        issues.append(Issue(level="warning", code="no_date", message="No document date found; please add it so the timeline is correct", path="document_date"))
    if ex.unreadable:
        issues.append(Issue(level="warning", code="unreadable", message="Some parts could not be read: " + "; ".join(ex.unreadable[:5])))
    if ex.patient.abha_number and not re.fullmatch(r"\d{2}-?\d{4}-?\d{4}-?\d{4}", ex.patient.abha_number.strip()):
        issues.append(Issue(level="warning", code="abha_format", message=f"ABHA number '{ex.patient.abha_number}' is not 14 digits", path="patient.abha_number"))

    payload = ReviewPayload(
        document=document,
        medications=build_medications(ex.medications),
        observations=build_observations(ex.tests, sex, doc_date),
        conditions=build_conditions(ex),
        encounter=enc,
        issues=issues,
    )
    if first is not None and verification is not None:
        _apply_agreement(payload, first, verification)
    payload.stats = compute_stats(payload)
    return payload


def refresh_review(p: ReviewPayload, sex: str | None) -> ReviewPayload:
    """Re-derive codes, flags and schedules after the user edits the review form."""
    dd = dosage()
    for o in p.observations:
        entry, _ = labs().match(o.name, o.name_raw)
        if entry:
            o.loinc = entry.loinc
            if o.unit and norm_unit(o.unit) != norm_unit(entry.unit) and o.value_num is not None:
                conv = entry.convert(o.value_num, o.unit)
                if conv:
                    factor_lo = entry.convert(o.ref_low, o.unit)[0] if o.ref_low is not None else None  # type: ignore[index]
                    factor_hi = entry.convert(o.ref_high, o.unit)[0] if o.ref_high is not None else None  # type: ignore[index]
                    o.value_num, o.unit, o.ref_low, o.ref_high = _round(conv[0]), entry.unit, _round(factor_lo), _round(factor_hi)
            if o.ref_low is None and o.ref_high is None and (not o.unit or norm_unit(o.unit) == norm_unit(entry.unit)):
                o.ref_low, o.ref_high = entry.ref_range(sex)
                o.ref_source = "curated"
                o.ref_text = _range_text(o.ref_low, o.ref_high, entry.unit) + " (standard adult range)"
        o.interpretation, o.critical = None, False
        if o.value_num is not None and (o.ref_low is not None or o.ref_high is not None):
            o.interpretation = "L" if (o.ref_low is not None and o.value_num < o.ref_low) else \
                "H" if (o.ref_high is not None and o.value_num > o.ref_high) else "N"
            bound = (o.value_text or "").strip()
            if (bound.startswith(("<", "≤")) and o.interpretation == "H") or (bound.startswith((">", "≥")) and o.interpretation == "L"):
                o.interpretation = None  # a bound-only result such as "<0.5" cannot be classified against this range
            if entry and entry.critical and (not o.unit or norm_unit(o.unit) == norm_unit(entry.unit)):
                clo, chi = entry.critical
                if clo is not None and o.value_num < clo:
                    o.interpretation, o.critical = "LL", True
                elif chi is not None and o.value_num > chi:
                    o.interpretation, o.critical = "HH", True
        elif o.value_text:
            low = o.value_text.lower()
            o.interpretation = "N" if any(w in low for w in _NEGATIVE) else "A" if any(w in low for w in _POSITIVE) else None
    for m in p.medications:
        drug, score, _ = drugs().match(m.name, m.name_raw, m.generic)
        if drug:
            m.generic, m.drug_class, m.common_use = drug.generic, drug.drug_class, drug.common_use
            m.dictionary_match, m.dictionary_score = drug.brand, round(score, 3)
        f = dd.parse_frequency(m.frequency_raw)
        if f["morning"] is not None:
            m.morning, m.afternoon, m.night = f["morning"], f["afternoon"], f["night"]
        if f["code"]:
            m.frequency_code, m.frequency_text = f["code"], f["text"]
        days = dd.parse_duration_days(m.duration_text)
        if days is not None:
            m.duration_days = days
    for c in p.conditions:
        hit, _ = icd10().match(c.name, c.name_raw)
        if hit:
            c.icd10, c.icd10_display = hit["code"], hit["display"]
    p.stats = compute_stats(p)
    return p


def compute_stats(p: ReviewPayload) -> ReviewStats:
    items = [*p.medications, *p.observations, *p.conditions]
    if not items:
        return ReviewStats()
    return ReviewStats(
        items_total=len(items),
        needs_review=sum(1 for i in items if i.needs_review),
        corrected_by_verifier=sum(1 for i in items if i.verified == "corrected"),
        added_by_verifier=sum(1 for i in items if i.verified == "added"),
        avg_confidence=round(sum(i.confidence for i in items) / len(items), 3),
    )
