"""ABDM-style FHIR Bundles: per-document `document` bundles and a patient `collection` export,
plus import of FHIR bundles (e.g. from an ABDM Health Information Provider) back into extractions.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.fhir import mapper
from app.models.tables import (
    Condition,
    DiagnosticReport,
    Document,
    Encounter,
    MedicationRequest,
    Observation,
    Patient,
)
from app.schemas.extraction import (
    DocumentExtraction,
    ExtractedDiagnosis,
    ExtractedEncounter,
    ExtractedMedication,
    ExtractedPatient,
    ExtractedTest,
)


def _entry(res: dict[str, Any]) -> dict[str, Any]:
    return {"fullUrl": f"urn:uuid:{res['id']}", "resource": res}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def document_bundle(db: Session, doc: Document) -> dict[str, Any]:
    patient = db.get(Patient, doc.patient_id)
    assert patient is not None
    review = doc.review or {}
    meta_doc = review.get("document", {})
    obs = db.exec(select(Observation).where(Observation.document_id == doc.id)).all()
    meds = db.exec(select(MedicationRequest).where(MedicationRequest.document_id == doc.id)).all()
    conds = db.exec(select(Condition).where(Condition.document_id == doc.id)).all()
    reports = db.exec(select(DiagnosticReport).where(DiagnosticReport.document_id == doc.id)).all()
    encs = db.exec(select(Encounter).where(Encounter.document_id == doc.id)).all()

    entries: list[dict[str, Any]] = []
    pat = mapper.patient_resource(patient)
    author_refs = []
    prac = org = None
    if doc.author:
        prac = mapper.practitioner_resource(doc.author, meta_doc.get("author_registration"))
        author_refs.append(mapper.ref("Practitioner", prac["id"]))
    if doc.facility:
        org = mapper.organization_resource(doc.facility)
        if not author_refs:
            author_refs.append(mapper.ref("Organization", org["id"]))
    if not author_refs:
        author_refs.append({"display": "Personal Health Copilot (patient-uploaded)"})

    code, display, profile = mapper.COMPOSITION_TYPES.get(doc.doc_type or "other", mapper.COMPOSITION_TYPES["other"])
    sections: list[dict[str, Any]] = []
    if meds:
        sections.append({"title": "Prescription", "code": {"coding": [{"system": mapper.SNOMED, "code": "440545006", "display": "Prescription record"}]},
                         "entry": [mapper.ref("MedicationRequest", m.id) for m in meds]})
    if conds:
        sections.append({"title": "Diagnoses", "code": {"coding": [{"system": mapper.SNOMED, "code": "439401001", "display": "Diagnosis"}]},
                         "entry": [mapper.ref("Condition", c.id) for c in conds]})
    if reports:
        sections.append({"title": "Investigations", "code": {"coding": [{"system": mapper.SNOMED, "code": "721981007", "display": "Diagnostic studies report"}]},
                         "entry": [mapper.ref("DiagnosticReport", r.id) for r in reports]})
    vitals = [o for o in obs if o.category == "vital-signs"]
    if vitals:
        sections.append({"title": "Vital signs", "entry": [mapper.ref("Observation", o.id) for o in vitals]})
    sections.append({"title": "Source document", "code": {"coding": [{"system": mapper.SNOMED, "code": "419891008", "display": "Record artifact"}]},
                     "entry": [mapper.ref("DocumentReference", doc.id)]})

    composition = mapper._clean({
        "resourceType": "Composition", "id": mapper.stable_id("composition", doc.id),
        "meta": {"profile": [mapper.NRCES + profile]},
        "identifier": {"system": "https://healthcopilot.local/composition", "value": doc.id},
        "status": "final",
        "type": {"coding": [{"system": mapper.SNOMED, "code": code, "display": display}], "text": display},
        "subject": mapper.ref("Patient", patient.id),
        "encounter": mapper.ref("Encounter", encs[0].id) if encs else None,
        "date": mapper.instant(doc.document_date) or mapper.instant(doc.created_at),
        "author": author_refs,
        "title": doc.title or display,
        "custodian": mapper.ref("Organization", org["id"]) if org else None,
        "section": sections,
    })
    entries.append(_entry(composition))
    entries.append(_entry(pat))
    for r in (prac, org):
        if r:
            entries.append(_entry(r))
    for row in [*encs, *meds, *conds, *reports, *obs]:
        if row.fhir_json:
            entries.append(_entry(row.fhir_json))
    entries.append(_entry(doc.fhir_json or mapper.document_reference_resource(doc)))
    return {
        "resourceType": "Bundle", "id": mapper.stable_id("bundle", doc.id),
        "meta": {"profile": [mapper.NRCES + "DocumentBundle"], "lastUpdated": _now()},
        "identifier": {"system": "https://healthcopilot.local/bundle", "value": doc.id},
        "type": "document", "timestamp": _now(), "entry": entries,
    }


def patient_bundle(db: Session, patient: Patient) -> dict[str, Any]:
    entries = [_entry(mapper.patient_resource(patient))]
    docs = db.exec(select(Document).where(Document.patient_id == patient.id, Document.status == "confirmed")).all()
    seen: set[str] = set()
    for d in docs:
        b = document_bundle(db, d)
        for e in b["entry"]:
            rid = e["resource"]["resourceType"] + "/" + e["resource"]["id"]
            if rid not in seen and e["resource"]["resourceType"] != "Patient":
                seen.add(rid)
                entries.append(e)
    return {
        "resourceType": "Bundle", "id": str(uuid.uuid4()),
        "meta": {"lastUpdated": _now()},
        "identifier": {"system": "https://healthcopilot.local/export", "value": patient.id},
        "type": "collection", "timestamp": _now(), "entry": entries,
    }


def validate_bundle(bundle: dict[str, Any]) -> list[str]:
    errors = mapper.validate_resource({k: v for k, v in bundle.items() if k != "entry"} | {"entry": []})
    for e in bundle.get("entry", []):
        errors.extend(mapper.validate_resource(e["resource"]))
    return errors


# ------------------------------------------------------------------ import

def _code_text(cc: dict[str, Any] | None) -> str:
    if not cc:
        return ""
    return cc.get("text") or next((c.get("display") for c in cc.get("coding", []) if c.get("display")), "") or ""


def _date(s: str | None) -> str | None:
    return s[:10] if s else None


def bundle_to_extractions(bundle: dict[str, Any]) -> list[tuple[DocumentExtraction, dict[str, Any]]]:
    """Each Composition in a document bundle becomes one DocumentExtraction (re-validated downstream)."""
    by_ref: dict[str, dict[str, Any]] = {}
    for e in bundle.get("entry", []):
        r = e["resource"]
        by_ref[e.get("fullUrl", "")] = r
        by_ref[f"{r['resourceType']}/{r.get('id')}"] = r
        by_ref[f"urn:uuid:{r.get('id')}"] = r

    comps = [e["resource"] for e in bundle.get("entry", []) if e["resource"]["resourceType"] == "Composition"]
    out: list[tuple[DocumentExtraction, dict[str, Any]]] = []
    patient = next((e["resource"] for e in bundle.get("entry", []) if e["resource"]["resourceType"] == "Patient"), {})
    for comp in comps:
        refs: list[dict[str, Any]] = []

        def collect(ref: dict[str, Any]) -> None:
            r = by_ref.get(ref.get("reference", ""))
            if r and r not in refs:
                refs.append(r)
                for child in r.get("result", []):
                    collect(child)

        for sec in comp.get("section", []):
            for ref in sec.get("entry", []):
                collect(ref)
        if comp.get("encounter"):
            collect(comp["encounter"])
        author = next((by_ref.get(a.get("reference", "")) for a in comp.get("author", [])), None)
        custodian = by_ref.get((comp.get("custodian") or {}).get("reference", ""))
        doc_date = _date(comp.get("date"))
        type_code = next((c.get("code") for c in comp.get("type", {}).get("coding", [])), None)
        doc_type = {"440545006": "prescription", "721981007": "lab_report", "373942005": "discharge_summary"}.get(type_code or "", "other")

        tests, meds, dx = [], [], []
        enc = None
        for r in refs:
            rt = r["resourceType"]
            if rt == "Observation":
                tests.append(_obs_to_test(r))
            elif rt == "MedicationRequest":
                meds.append(_medreq_to_med(r))
            elif rt == "Condition":
                status = next((c.get("code") for c in r.get("verificationStatus", {}).get("coding", [])), "confirmed")
                dx.append(ExtractedDiagnosis(
                    text_as_written=_code_text(r.get("code")), name=_code_text(r.get("code")),
                    icd10=next((c.get("code") for c in r.get("code", {}).get("coding", []) if "icd" in c.get("system", "")), None),
                    status="provisional" if status == "provisional" else "confirmed", confidence=1.0, page=1,
                ))
            elif rt == "Encounter" and r.get("class", {}).get("code") == "IMP":
                enc = ExtractedEncounter(
                    admission_date=_date(r.get("period", {}).get("start")), discharge_date=_date(r.get("period", {}).get("end")),
                    reason_for_admission=", ".join(x.get("text", "") for x in r.get("reasonCode", [])) or None,
                    hospital_course=None, procedures=[], discharge_condition=None,
                )
        conclusion = next((r.get("conclusion") for r in refs if r["resourceType"] == "DiagnosticReport" and r.get("conclusion")), None)
        ex = DocumentExtraction(
            document_type=doc_type, document_date_as_written=None, document_date=doc_date,
            facility_name=(custodian or {}).get("name"),
            doctor_name=_name(author) if author and author.get("resourceType") == "Practitioner" else None,
            doctor_registration=next((i.get("value") for i in (author or {}).get("identifier", [])), None) if author and author.get("resourceType") == "Practitioner" else None,
            patient=ExtractedPatient(name=_name(patient), age=None, gender=patient.get("gender"), patient_identifier=None,
                                     abha_number=next((i.get("value") for i in patient.get("identifier", []) if "healthid" in i.get("system", "") and re.search(r"\d{2}-\d{4}", i.get("value", ""))), None)),
            diagnoses=dx, medications=meds, tests=tests, encounter=enc, findings=None, impression=conclusion,
            advice=[], follow_up=None, unreadable=[], legibility="good",
        )
        out.append((ex, {"title": comp.get("title"), "composition_id": comp.get("id")}))
    return out


def _name(r: dict[str, Any] | None) -> str | None:
    if not r:
        return None
    n = (r.get("name") or [{}])
    if isinstance(n, str):
        return n
    n0 = n[0]
    return n0.get("text") or " ".join([*n0.get("given", []), n0.get("family", "")]).strip() or None


def _obs_to_test(r: dict[str, Any]) -> ExtractedTest:
    q = r.get("valueQuantity")
    rr = (r.get("referenceRange") or [{}])[0]
    lo, hi = (rr.get("low") or {}).get("value"), (rr.get("high") or {}).get("value")
    ref_text = rr.get("text") or (f"{lo} - {hi}" if lo is not None and hi is not None else f"< {hi}" if hi is not None else f"> {lo}" if lo is not None else None)
    cat = next((c.get("code") for cc in r.get("category", []) for c in cc.get("coding", [])), "laboratory")
    name = next((c.get("display") for c in r.get("code", {}).get("coding", []) if c.get("display")), None) or _code_text(r.get("code"))
    return ExtractedTest(
        category="vital-signs" if cat == "vital-signs" else "laboratory", panel=None,
        test_name_as_written=_code_text(r.get("code")) or name, test_name=name,
        value_as_written=str(q["value"]) if q else (r.get("valueString") or ""),
        value_numeric=float(q["value"]) if q else None, unit=(q or {}).get("unit"),
        reference_range_as_written=ref_text, ref_low=lo, ref_high=hi, flag_on_report=None, confidence=1.0, page=1,
    )


def _medreq_to_med(r: dict[str, Any]) -> ExtractedMedication:
    text = _code_text(r.get("medicationCodeableConcept"))
    m = re.match(r"^(.*?)\s+(\d+(?:\.\d+)?\s*(?:mg|mcg|g|iu|ml)\b.*?)?(?:\s*\((.+)\))?$", text, re.I)
    name, strength, generic = (m.group(1), m.group(2), m.group(3)) if m else (text, None, None)
    di = (r.get("dosageInstruction") or [{}])[0]
    timing = di.get("timing", {})
    rep = timing.get("repeat", {})
    when = rep.get("when", [])
    freq_text = (timing.get("code") or {}).get("text")
    meal = " ".join(x.get("text", "") for x in di.get("additionalInstruction", [])).lower()
    meal_rel = "before_food" if "before" in meal else "after_food" if "after" in meal else "empty_stomach" if "empty" in meal else None
    days = (rep.get("boundsDuration") or {}).get("value")
    return ExtractedMedication(
        name_as_written=text, name=(name or text).strip(), generic_name=generic, strength=(strength or "").strip() or None,
        form=None, dose=None, frequency_as_written=freq_text,
        morning=1.0 if "MORN" in when else (0.0 if when else None), afternoon=1.0 if "AFT" in when else (0.0 if when else None),
        night=1.0 if "NIGHT" in when else (0.0 if when else None), meal_relation=meal_rel, route=(di.get("route") or {}).get("text"),
        duration_as_written=f"{int(days)} days" if days else None, duration_days=int(days) if days else None,
        instructions=None, confidence=1.0, page=1,
    )
