"""'Ask my records': grounded Q&A over the patient's own structured records."""

import json
from typing import Any

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.models.tables import Condition, Document, MedicationRequest, Observation, Patient
from app.pipeline import llm
from app.services import facts as F
from app.services.safety import EMERGENCY_NOTICE, LANGUAGES, check_text, is_emergency, redact


class ChatAnswer(BaseModel):
    answer: str = Field(description="Answer in the requested language, plain and short (max ~150 words)")
    cited_record_ids: list[str] = Field(description="IDs of records used for the answer")
    answered_from_records: bool = Field(description="False if the records do not contain the answer")
    suggest_doctor: bool = Field(description="True if the question needs a clinician's judgement")


CHAT_SYSTEM = """You are a careful personal health copilot. You answer questions about the user's OWN health records.
RECORDS (JSON) are provided; every record has an `id`.
Rules:
- Answer from the records first and cite the ids you used. Quote values and dates exactly as in the records.
- If the records do not contain the answer, say so plainly. You may add brief, well-established general health information, clearly labelled as general information.
- Never diagnose. Never tell the user to start, stop, skip or change a medicine or dose; for such questions explain what the record says and advise asking their doctor.
- For worrying symptoms, advise contacting a doctor; for emergency symptoms, advise calling 112.
- Be warm, calm and brief. Reply in {language}. Keep drug names, numbers and units unchanged.
"""


def _records(db: Session, patient: Patient) -> dict[str, Any]:
    docs = db.exec(select(Document).where(Document.patient_id == patient.id, Document.status == "confirmed")).all()
    obs = db.exec(select(Observation).where(Observation.patient_id == patient.id)).all()
    meds = db.exec(select(MedicationRequest).where(MedicationRequest.patient_id == patient.id)).all()
    conds = db.exec(select(Condition).where(Condition.patient_id == patient.id)).all()
    obs = sorted(obs, key=lambda o: o.effective_date.isoformat() if o.effective_date else "", reverse=True)[:200]
    return {
        "patient": {"gender": patient.gender, "abha_linked": bool(patient.abha_number)},
        "documents": [{"id": d.id, "type": d.doc_type, "title": d.title, "date": d.document_date.isoformat() if d.document_date else None,
                       "facility": d.facility, "doctor": d.author} for d in docs],
        "conditions": [F.cond_fact(c) for c in conds],
        "medications": [F.med_fact(m) for m in meds],
        "results": [F.obs_fact(o) for o in obs],
    }


def _label_index(db: Session, patient: Patient) -> dict[str, dict[str, Any]]:
    idx: dict[str, dict[str, Any]] = {}
    for d in db.exec(select(Document).where(Document.patient_id == patient.id)).all():
        idx[d.id] = {"kind": "document", "label": d.title or d.doc_type, "date": d.document_date, "document_id": d.id}
    for o in db.exec(select(Observation).where(Observation.patient_id == patient.id)).all():
        idx[o.id] = {"kind": "result", "label": f"{o.name}: {o.value_num if o.value_num is not None else o.value_text} {o.unit or ''}".strip(),
                     "date": o.effective_date, "document_id": o.document_id}
    for m in db.exec(select(MedicationRequest).where(MedicationRequest.patient_id == patient.id)).all():
        idx[m.id] = {"kind": "medication", "label": f"{m.name} {m.strength or ''}".strip(), "date": m.authored_on, "document_id": m.document_id}
    for c in db.exec(select(Condition).where(Condition.patient_id == patient.id)).all():
        idx[c.id] = {"kind": "condition", "label": c.name, "date": c.recorded_date, "document_id": c.document_id}
    return idx


def ask(db: Session, patient: Patient, message: str, history: list[dict[str, str]], lang: str = "en") -> dict[str, Any]:
    records = _records(db, patient)
    convo = "\n".join(f"{h['role'].upper()}: {h['content']}" for h in history[-6:])
    prompt = f"RECORDS:\n{json.dumps(records, ensure_ascii=False, default=str)}\n\nCONVERSATION SO FAR:\n{convo}\n\nUSER QUESTION: {message}"
    system = CHAT_SYSTEM.format(language=LANGUAGES.get(lang, "English"))
    r: ChatAnswer = llm.parse("fast", system, prompt, ChatAnswer).parsed
    safety = check_text(r.answer)
    answer = r.answer if safety.passed else redact(r.answer)
    idx = _label_index(db, patient)
    citations = []
    for rid in dict.fromkeys(r.cited_record_ids):
        if rid in idx:
            c = idx[rid]
            citations.append({"id": rid, **c, "date": c["date"].isoformat() if c["date"] else None})
    return {
        "answer": answer,
        "citations": citations,
        "answered_from_records": r.answered_from_records,
        "suggest_doctor": r.suggest_doctor,
        "emergency_notice": EMERGENCY_NOTICE.get(lang, EMERGENCY_NOTICE["en"]) if is_emergency(message) else None,
        "safety": {"passed": safety.passed, "violations": safety.violations},
    }
