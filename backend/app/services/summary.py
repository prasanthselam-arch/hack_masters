"""Plain-language summaries grounded in the fact sheet, with safety checks and translation.

The LLM writes prose only. Values, flags, critical alerts, schedules and disclaimers are
attached from the database / code, so a summary can never show a number the record does not have.
"""

import hashlib
import json
import logging
from typing import Any

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.models.tables import Document, MedicationRequest, Observation, Patient, Summary
from app.pipeline import llm
from app.pipeline.validate import _range_text
from app.services import facts as F
from app.services.records import medication_status
from app.services.safety import CRITICAL_BANNER, DISCLAIMER, LANGUAGES, check_text, numbers_in, numbers_preserved, redact

log = logging.getLogger(__name__)
PROMPT_VERSION = "v3"


class KeyPoint(BaseModel):
    text: str
    record_ids: list[str] = Field(description="IDs from the facts that support this point")


class AbnormalExplanation(BaseModel):
    record_id: str
    test: str
    what_it_measures: str = Field(description="One short plain sentence")
    what_this_may_mean: str = Field(description="1-2 sentences, hedged ('can be seen with', 'may'), based on the provided high_can_mean/low_can_mean")
    questions_for_doctor: list[str]


class MedicationExplanation(BaseModel):
    record_id: str
    name: str
    commonly_used_for: str = Field(description="Use 'commonly used for ...' wording; never claim why THIS patient takes it unless the facts say so")
    how_to_take: str = Field(description="Plain restatement of the schedule, meal timing and duration from the facts")


class GlossaryItem(BaseModel):
    term: str
    meaning: str


class SummaryText(BaseModel):
    headline: str = Field(description="One calm sentence, max 20 words")
    overview: str = Field(description="2-4 short sentences in plain language")
    key_points: list[KeyPoint]
    abnormal: list[AbnormalExplanation] = Field(description="Only results whose flag is not normal")
    medications: list[MedicationExplanation]
    trends: list[KeyPoint] = Field(description="Changes over time; empty if no trend data")
    next_steps: list[str] = Field(description="Practical, safe next steps: follow-up, tests advised in the document, lifestyle points written by the doctor")
    questions_for_doctor: list[str]
    glossary: list[GlossaryItem]


SUMMARY_SYSTEM = """You explain medical records to patients in India in simple, warm, plain English (about a 12-year-old's reading level).

You receive FACTS (JSON) extracted from the patient's own records. Rules:
1. Use ONLY the facts. Do not add test values, dates, diagnoses or medicines that are not in the facts.
2. Flags (normal/high/low/critical) are already computed. Never re-decide them; explain only results whose flag is not normal.
3. For abnormal results, base 'what this may mean' on the provided `high_can_mean` / `low_can_mean` text and hedge ("can be seen with", "may"). Never state the patient has a disease unless it is listed in `conditions`.
4. Never advise starting, stopping, skipping or changing any medicine or dose. You may say "take medicines as prescribed" and "discuss with your doctor".
5. For critical results, say clearly and calmly that the doctor should be contacted promptly.
6. Avoid jargon; when a medical term is needed, explain it (add it to the glossary).
7. Refer to supporting record IDs in `record_ids` / `record_id` exactly as given.
8. Do not include a disclaimer (it is added separately).
"""

PATIENT_EXTRA = """These FACTS cover the patient's whole record: conditions, active medicines, the latest value of each test and trends over time.
Write an overall picture: what is going well, what needs attention, and how values are changing. Mention trend direction using the provided direction and dates."""

TRANSLATE_SYSTEM = """You translate patient-facing health summaries from English into {language}.
Rules:
- Natural, simple, everyday {language} that an average patient understands (not overly formal or Sanskritised).
- After a medical term, keep the English term in brackets the first time, e.g. "हीमोग्लोबिन (Hemoglobin)".
- Keep every number, unit, date, drug/brand name and record ID exactly as in the source. Do not add or drop information.
- Translate every string field; keep `record_id`/`record_ids` unchanged.
"""


def _hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:24]


def _generate(facts: dict[str, Any], patient_level: bool) -> tuple[SummaryText, dict[str, Any]]:
    system = SUMMARY_SYSTEM + ("\n" + PATIENT_EXTRA if patient_level else "")
    prompt = "FACTS:\n" + json.dumps(facts, ensure_ascii=False, default=str)
    allowed = numbers_in(facts)
    safety: dict[str, Any] = {"regenerated": False, "redacted": False, "violations": []}
    for attempt in range(2):
        s: SummaryText = llm.parse("fast", system, prompt, SummaryText).parsed
        text_blob = json.dumps(s.model_dump(), ensure_ascii=False)
        rep = check_text(text_blob, allowed)
        if rep.passed:
            return s, safety
        safety["violations"] = rep.violations + [f"ungrounded number {n}" for n in rep.ungrounded_numbers]
        log.warning("summary safety issue (attempt %d): %s", attempt + 1, safety["violations"])
        if attempt == 0:
            safety["regenerated"] = True
            prompt += ("\n\nYOUR PREVIOUS DRAFT BROKE THESE RULES; fix them: " + "; ".join(safety["violations"])
                       + ". Use only numbers present in the facts and never advise changing medicines.")
    # last resort: strip offending sentences
    data = s.model_dump()
    data = _redact_obj(data)
    safety["redacted"] = True
    return SummaryText.model_validate(data), safety


def _redact_obj(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: (v if k in ("record_id", "record_ids") else _redact_obj(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [_redact_obj(x) for x in o]
    if isinstance(o, str):
        return redact(o)
    return o


def translate(summary: SummaryText, lang: str) -> tuple[SummaryText, bool]:
    if lang == "en":
        return summary, True
    system = TRANSLATE_SYSTEM.format(language=LANGUAGES[lang])
    src = summary.model_dump()
    out: SummaryText = summary
    ok = False
    for _ in range(2):
        out = llm.parse("fast", system, "SOURCE (English JSON):\n" + json.dumps(src, ensure_ascii=False), SummaryText).parsed
        ok = numbers_preserved(json.dumps(_strip_ids(src), ensure_ascii=False), json.dumps(_strip_ids(out.model_dump()), ensure_ascii=False))
        if ok:
            break
        log.warning("translation to %s changed numbers; retrying", lang)
    # keep IDs authoritative from the source
    for a, b in zip(out.abnormal, summary.abnormal):
        a.record_id = b.record_id
    for a, b in zip(out.medications, summary.medications):
        a.record_id = b.record_id
    return out, ok


def _strip_ids(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _strip_ids(v) for k, v in o.items() if k not in ("record_id", "record_ids")}
    if isinstance(o, list):
        return [_strip_ids(x) for x in o]
    return o


def _assemble(db: Session, text: SummaryText, lang: str, facts: dict[str, Any], safety: dict[str, Any], numbers_ok: bool) -> dict[str, Any]:
    """Attach authoritative values from the DB to the generated prose."""
    obs_ids = [a.record_id for a in text.abnormal]
    obs = {o.id: o for o in db.exec(select(Observation).where(Observation.id.in_(obs_ids))).all()} if obs_ids else {}  # type: ignore[attr-defined]
    med_ids = [m.record_id for m in text.medications]
    meds = {m.id: m for m in db.exec(select(MedicationRequest).where(MedicationRequest.id.in_(med_ids))).all()} if med_ids else {}  # type: ignore[attr-defined]
    abnormal = []
    for a in text.abnormal:
        o = obs.get(a.record_id)
        if o is None or o.interpretation in (None, "N"):
            continue  # never show an "abnormal" explanation the data does not support
        reference = o.ref_text or (_range_text(o.ref_low, o.ref_high, o.unit) if o.ref_low is not None or o.ref_high is not None else None)
        abnormal.append({**a.model_dump(), "value": o.value_text or o.value_num, "unit": o.unit,
                         "reference": reference, "flag": o.interpretation, "critical": o.critical,
                         "date": o.effective_date.isoformat() if o.effective_date else None})
    medications = []
    for m in text.medications:
        row = meds.get(m.record_id)
        if row is None:
            continue
        medications.append({**m.model_dump(), "strength": row.strength, "morning": row.morning, "afternoon": row.afternoon,
                            "night": row.night, "meal_relation": row.meal_relation, "duration_days": row.duration_days,
                            "frequency": row.frequency_raw, "status": medication_status(row)})
    criticals = [r for r in (facts.get("results") or facts.get("latest_results") or []) if r.get("critical")]
    return {
        **text.model_dump(), "abnormal": abnormal, "medications": medications,
        "language": lang, "disclaimer": DISCLAIMER[lang],
        "critical_alert": CRITICAL_BANNER[lang] if criticals else None,
        "critical_results": [{"id": r["id"], "test": r["test"], "value": r.get("value"), "unit": r.get("unit"), "flag": r.get("flag")} for r in criticals],
        "safety": {**safety, "numbers_preserved": numbers_ok},
        "grounded_on": {"results": len(facts.get("results") or facts.get("latest_results") or []),
                        "medications": len(facts.get("medications") or facts.get("active_medications") or []),
                        "conditions": len(facts.get("conditions") or [])},
    }


def _find(db: Session, patient_id: str, document_id: str | None, scope: str, lang: str, source_hash: str) -> Summary | None:
    q = select(Summary).where(Summary.patient_id == patient_id, Summary.scope == scope, Summary.language == lang,
                              Summary.source_hash == source_hash)
    q = q.where(Summary.document_id == document_id) if document_id else q.where(Summary.document_id.is_(None))  # type: ignore[union-attr]
    return db.exec(q).first()


def _get_or_build(db: Session, patient_id: str, document_id: str | None, scope: str, facts: dict[str, Any], lang: str) -> dict[str, Any]:
    source_hash = _hash([PROMPT_VERSION, facts])
    cached = _find(db, patient_id, document_id, scope, lang, source_hash)
    if cached:
        return cached.content

    def store(language: str, content: dict[str, Any]) -> None:
        db.add(Summary(patient_id=patient_id, document_id=document_id, scope=scope, language=language,
                       source_hash=source_hash, content=content))
        db.commit()

    # English is the source of truth; other languages are translations of it.
    en_row = _find(db, patient_id, document_id, scope, "en", source_hash)
    if en_row:
        en = SummaryText.model_validate(en_row.content["_text"])
        safety = en_row.content.get("safety", {})
    else:
        en, safety = _generate(facts, scope == "patient")
        content_en = _assemble(db, en, "en", facts, safety, True) | {"_text": en.model_dump()}
        store("en", content_en)
        if lang == "en":
            return content_en
    text, numbers_ok = translate(en, lang)
    content = _assemble(db, text, lang, facts, {k: v for k, v in safety.items() if k != "numbers_preserved"}, numbers_ok)
    store(lang, content)
    return content


def document_summary(db: Session, doc: Document, lang: str = "en") -> dict[str, Any]:
    facts = F.document_facts(db, doc)
    return _get_or_build(db, doc.patient_id, doc.id, "document", facts, lang)


def patient_summary(db: Session, patient: Patient, lang: str = "en") -> dict[str, Any]:
    facts = F.patient_facts(db, patient)
    return _get_or_build(db, patient.id, None, "patient", facts, lang)
