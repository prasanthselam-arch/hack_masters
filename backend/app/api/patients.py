from collections import defaultdict
from datetime import date, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from sqlmodel import Session, select

from app.api.deps import current_account, patient_or_404
from app.db import get_session
from app.fhir import mapper
from app.fhir.bundle import patient_bundle
from app.knowledge import labs
from app.models.tables import Account, Condition, Document, Encounter, MedicationRequest, Observation, Patient
from app.services import contact
from app.services.records import delete_patient as delete_patient_data
from app.services.records import medication_status
from app.services.safety import LANGUAGES

router = APIRouter(prefix="/api/patients", tags=["patients"])


GENDERS = {"male", "female", "other", "unknown"}
RELATIONSHIPS = {"self", "spouse", "father", "mother", "son", "daughter", "brother", "sister", "grandfather",
                 "grandmother", "grandson", "granddaughter", "father_in_law", "mother_in_law", "other"}


class PatientFields(BaseModel):
    @field_validator("name", check_fields=False)
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = " ".join(v.split())
        if not v:
            raise ValueError("Please enter a name")
        if len(v) > 100:
            raise ValueError("Name is too long")
        return v

    @field_validator("gender", check_fields=False)
    @classmethod
    def _gender(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if v not in GENDERS:
            raise ValueError("Unknown gender")
        return v

    @field_validator("birth_date", check_fields=False)
    @classmethod
    def _birth_date(cls, v: date | None) -> date | None:
        if v is not None and not date(1900, 1, 1) <= v <= date.today():
            raise ValueError("Date of birth must be between 1900 and today")
        return v

    @field_validator("phone", check_fields=False)
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        try:
            return contact.normalize_phone(v)
        except contact.ContactError as e:
            raise ValueError(str(e)) from e

    @field_validator("preferred_language", check_fields=False)
    @classmethod
    def _lang(cls, v: str | None) -> str | None:
        if v is not None and v not in LANGUAGES:
            raise ValueError("Unsupported language")
        return v

    @field_validator("relationship", check_fields=False)
    @classmethod
    def _relationship(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if v not in RELATIONSHIPS:
            raise ValueError("Unknown relationship")
        return v


class PatientIn(PatientFields):
    name: str
    gender: str | None = None
    birth_date: date | None = None
    phone: str | None = None
    preferred_language: str = "en"
    relationship: str | None = None


class PatientPatch(PatientFields):
    name: str | None = None
    gender: str | None = None
    birth_date: date | None = None
    phone: str | None = None
    preferred_language: str | None = None
    relationship: str | None = None


def _patient_out(p: Patient) -> dict[str, Any]:
    return p.model_dump(exclude={"fhir_json"})


@router.get("")
def list_patients(acc: Account = Depends(current_account), db: Session = Depends(get_session)):
    rows = db.exec(select(Patient).where(Patient.owner_id == acc.id).order_by(Patient.created_at)).all()
    return [_patient_out(p) for p in rows]


def _self_profile(db: Session, owner_id: str | None) -> Patient | None:
    return db.exec(select(Patient).where(Patient.owner_id == owner_id, Patient.relationship == "self")).first()


@router.post("")
def create_patient(body: PatientIn, acc: Account = Depends(current_account), db: Session = Depends(get_session)):
    p = Patient(**body.model_dump(), owner_id=acc.id)
    if p.relationship is None and not db.exec(select(Patient).where(Patient.owner_id == acc.id)).first():
        p.relationship = "self"
    if p.relationship == "self" and _self_profile(db, acc.id):
        raise HTTPException(409, "Your own profile already exists; choose how this person is related to you")
    p.fhir_json = mapper.patient_resource(p)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _patient_out(p)


@router.get("/{patient_id}")
def get_patient(p: Patient = Depends(patient_or_404)):
    return _patient_out(p)


@router.patch("/{patient_id}")
def update_patient(body: PatientPatch, p: Patient = Depends(patient_or_404), db: Session = Depends(get_session)):
    changes = body.model_dump(exclude_unset=True)
    if changes.get("name", "") is None or changes.get("preferred_language", "") is None:
        raise HTTPException(422, "Name and language cannot be empty")
    if "relationship" in changes and (changes["relationship"] == "self") != (p.relationship == "self"):
        if p.relationship == "self":
            raise HTTPException(409, "Your own profile is always 'self'")
        if _self_profile(db, p.owner_id):
            raise HTTPException(409, "Your own profile already exists; choose how this person is related to you")
    for k, v in changes.items():
        setattr(p, k, v)
    p.fhir_json = mapper.patient_resource(p)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _patient_out(p)


@router.delete("/{patient_id}")
def delete_patient(p: Patient = Depends(patient_or_404), db: Session = Depends(get_session)):
    if p.relationship == "self":
        raise HTTPException(409, "Your own profile can only be removed by deleting your account")
    delete_patient_data(db, p)
    return {"deleted": True}


def _obs_out(o: Observation) -> dict[str, Any]:
    return o.model_dump(exclude={"fhir_json"})


def _med_out(m: MedicationRequest) -> dict[str, Any]:
    return {**m.model_dump(exclude={"fhir_json"}), "status": medication_status(m)}


@router.get("/{patient_id}/profile")
def profile(p: Patient = Depends(patient_or_404), db: Session = Depends(get_session)):
    docs = db.exec(select(Document).where(Document.patient_id == p.id)).all()
    confirmed = [d for d in docs if d.status == "confirmed"]
    meds = db.exec(select(MedicationRequest).where(MedicationRequest.patient_id == p.id)).all()
    conds = db.exec(select(Condition).where(Condition.patient_id == p.id)).all()
    obs = db.exec(select(Observation).where(Observation.patient_id == p.id)).all()

    latest: dict[str, Observation] = {}
    for o in sorted(obs, key=lambda o: o.effective_date or date.min):
        latest[o.loinc or o.name.lower()] = o
    abnormal = sorted([o for o in latest.values() if o.interpretation not in (None, "N")],
                      key=lambda o: (not o.critical, -(o.effective_date or date.min).toordinal()))
    unique_conditions: dict[str, Condition] = {}
    for c in sorted(conds, key=lambda c: c.recorded_date or date.min):
        unique_conditions[c.icd10 or c.name.lower()] = c
    # The same prescription saved twice gives two active rows per drug; show each drug and strength once.
    active_by_drug: dict[tuple[str, str], MedicationRequest] = {}
    for m in sorted((m for m in meds if medication_status(m) == "active"), key=lambda m: m.authored_on or date.min, reverse=True):
        active_by_drug.setdefault(((m.generic or m.name).lower(), (m.strength or "").replace(" ", "").lower()), m)
    active = list(active_by_drug.values())
    vitals = {o.name: o for o in sorted([o for o in obs if o.category == "vital-signs"], key=lambda o: o.effective_date or date.min)}
    return {
        "patient": _patient_out(p),
        "counts": {"documents": len(confirmed), "pending_review": sum(1 for d in docs if d.status == "review"),
                   "processing": sum(1 for d in docs if d.status in ("queued", "processing")),
                   "results": len(obs), "medications": len(active), "conditions": len(unique_conditions)},
        "critical": [_obs_out(o) for o in latest.values() if o.critical],
        "abnormal_latest": [_obs_out(o) for o in abnormal[:12]],
        "active_medications": [_med_out(m) for m in active],
        "conditions": [c.model_dump(exclude={"fhir_json"}) for c in unique_conditions.values()],
        "latest_vitals": [_obs_out(o) for o in vitals.values()],
        "last_record_date": max((d.document_date for d in confirmed if d.document_date), default=None),
    }


@router.get("/{patient_id}/timeline")
def timeline(p: Patient = Depends(patient_or_404), db: Session = Depends(get_session)):
    docs = db.exec(select(Document).where(Document.patient_id == p.id)).all()
    obs = db.exec(select(Observation).where(Observation.patient_id == p.id)).all()
    meds = db.exec(select(MedicationRequest).where(MedicationRequest.patient_id == p.id)).all()
    conds = db.exec(select(Condition).where(Condition.patient_id == p.id)).all()
    encs = db.exec(select(Encounter).where(Encounter.patient_id == p.id)).all()
    by_doc_obs: dict[str, list[Observation]] = defaultdict(list)
    for o in obs:
        by_doc_obs[o.document_id or ""].append(o)
    by_doc_meds: dict[str, list[MedicationRequest]] = defaultdict(list)
    for m in meds:
        by_doc_meds[m.document_id or ""].append(m)
    by_doc_cond: dict[str, list[Condition]] = defaultdict(list)
    for c in conds:
        by_doc_cond[c.document_id or ""].append(c)
    by_doc_enc = {e.document_id: e for e in encs}
    events = []
    for d in docs:
        o = by_doc_obs.get(d.id, [])
        e = by_doc_enc.get(d.id)
        events.append({
            "id": d.id, "date": d.document_date or (d.created_at.replace(tzinfo=timezone.utc).astimezone(mapper.IST).date() if d.created_at else None),
            "date_known": d.document_date is not None,
            "type": d.doc_type or "other", "title": d.title or d.filename, "status": d.status, "source": d.source,
            "facility": d.facility, "author": d.author, "languages": d.languages, "handwritten": d.handwritten,
            "abnormal_count": sum(1 for x in o if x.interpretation not in (None, "N")),
            "critical_count": sum(1 for x in o if x.critical),
            "highlights": [{"name": x.name, "value": x.value_text or x.value_num, "unit": x.unit,
                            "flag": x.interpretation} for x in sorted(o, key=lambda x: x.interpretation in (None, "N"))[:4]],
            "medications": [f"{m.name} {m.strength or ''}".strip() for m in by_doc_meds.get(d.id, [])][:5],
            "conditions": [c.name for c in by_doc_cond.get(d.id, [])][:4],
            "encounter": {"class": e.encounter_class, "start": e.start_date, "end": e.end_date} if e else None,
        })
    events.sort(key=lambda x: (x["date"] or date.min), reverse=True)
    return events


@router.get("/{patient_id}/medications")
def medications(status: str | None = None, p: Patient = Depends(patient_or_404), db: Session = Depends(get_session)):
    rows = db.exec(select(MedicationRequest).where(MedicationRequest.patient_id == p.id)).all()
    if status:
        rows = [m for m in rows if medication_status(m) == status]
    rows = sorted(rows, key=lambda m: m.authored_on or date.min, reverse=True)
    return [_med_out(m) for m in rows]


@router.get("/{patient_id}/observations")
def observations(loinc: str | None = None, p: Patient = Depends(patient_or_404), db: Session = Depends(get_session)):
    q = select(Observation).where(Observation.patient_id == p.id)
    if loinc:
        q = q.where(Observation.loinc == loinc)
    rows = sorted(db.exec(q).all(), key=lambda o: o.effective_date or date.min, reverse=True)
    return [_obs_out(o) for o in rows]


@router.get("/{patient_id}/trends")
def trends(p: Patient = Depends(patient_or_404), db: Session = Depends(get_session)):
    rows = db.exec(select(Observation).where(Observation.patient_id == p.id, Observation.value_num.is_not(None))).all()  # type: ignore[union-attr]
    groups: dict[str, list[Observation]] = defaultdict(list)
    for o in rows:
        groups[o.loinc or o.name.lower()].append(o)
    out = []
    for key, items in groups.items():
        items.sort(key=lambda o: o.effective_date or date.min)
        units = {o.unit for o in items}
        entry = labs().by_loinc.get(items[-1].loinc or "")
        lo, hi = (items[-1].ref_low, items[-1].ref_high)
        out.append({
            "key": key, "name": items[-1].name, "loinc": items[-1].loinc, "unit": items[-1].unit,
            "panel": items[-1].panel or (entry.panel if entry else None), "category": items[-1].category,
            "mixed_units": len(units) > 1, "ref_low": lo, "ref_high": hi,
            "about": entry.what if entry else None,
            "latest": _obs_out(items[-1]),
            "points": [{"id": o.id, "document_id": o.document_id, "date": o.effective_date, "value": o.value_num, "unit": o.unit,
                        "flag": o.interpretation, "ref_low": o.ref_low, "ref_high": o.ref_high} for o in items],
        })
    out.sort(key=lambda t: (-len(t["points"]), t["latest"]["interpretation"] in (None, "N"), t["name"]))
    return out


@router.get("/{patient_id}/fhir")
def export_fhir(p: Patient = Depends(patient_or_404), db: Session = Depends(get_session)):
    bundle = patient_bundle(db, p)
    return JSONResponse(bundle, media_type="application/fhir+json",
                        headers={"Content-Disposition": f'attachment; filename="health-record-{p.id[:8]}.fhir.json"'})
