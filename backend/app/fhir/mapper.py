"""Map FHIR-shaped tables to FHIR R4 resources following ABDM / NRCeS profiles.

Profiles: https://nrces.in/ndhm/fhir/r4/ (Patient, Practitioner, Organization, Observation,
MedicationRequest, Condition, DiagnosticReportLab, Encounter, DocumentReference, Composition).
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.models.tables import (
    Condition,
    DiagnosticReport,
    Document,
    Encounter,
    MedicationRequest,
    Observation,
    Patient,
)

NRCES = "https://nrces.in/ndhm/fhir/r4/StructureDefinition/"
LOINC = "http://loinc.org"
SNOMED = "http://snomed.info/sct"
ICD10 = "http://hl7.org/fhir/sid/icd-10"
UCUM = "http://unitsofmeasure.org"
ABHA_SYSTEM = "https://healthid.ndhm.gov.in"
ABHA_ADDRESS_SYSTEM = "https://healthid.ndhm.gov.in/abha-address"
DOCTOR_SYSTEM = "https://doctor.ndhm.gov.in"
FACILITY_SYSTEM = "https://facility.ndhm.gov.in"
INTERP = "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation"
TZ = "+05:30"
IST = timezone(timedelta(hours=5, minutes=30))

UCUM_CODES = {
    "g/dL": "g/dL", "%": "%", "fL": "fL", "pg": "pg", "10^3/uL": "10*3/uL", "10^6/uL": "10*6/uL",
    "mm/h": "mm/h", "mg/dL": "mg/dL", "mmol/L": "mmol/L", "U/L": "U/L", "uIU/mL": "u[IU]/mL",
    "ng/dL": "ng/dL", "ug/dL": "ug/dL", "ng/mL": "ng/mL", "pg/mL": "pg/mL", "mg/L": "mg/L",
    "mL/min/1.73m2": "mL/min/{1.73_m2}", "mmHg": "mm[Hg]", "/min": "/min", "degF": "[degF]",
    "kg": "kg", "cm": "cm", "kg/m2": "kg/m2",
}
INTERP_DISPLAY = {"N": "Normal", "L": "Low", "H": "High", "LL": "Critical low", "HH": "Critical high", "A": "Abnormal"}

# Composition / document types (SNOMED CT) used by ABDM health-information types
COMPOSITION_TYPES = {
    "prescription": ("440545006", "Prescription record", "PrescriptionRecord"),
    "lab_report": ("721981007", "Diagnostic studies report", "DiagnosticReportRecord"),
    "imaging_report": ("721981007", "Diagnostic studies report", "DiagnosticReportRecord"),
    "discharge_summary": ("373942005", "Discharge summary", "DischargeSummaryRecord"),
    "other": ("419891008", "Record artifact", "HealthDocumentRecord"),
}


def stable_id(*parts: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "healthcopilot:" + ":".join(parts)))


def ref(resource_type: str, rid: str) -> dict[str, str]:
    return {"reference": f"urn:uuid:{rid}", "type": resource_type}


def dt(d: date | None) -> str | None:
    return d.isoformat() if d else None


def instant(d: date | datetime | None) -> str | None:
    if d is None:
        return None
    if isinstance(d, datetime):
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(IST).replace(microsecond=0).isoformat()  # stored times are UTC
    return f"{d.isoformat()}T00:00:00{TZ}"


def _clean(d: dict[str, Any]) -> dict[str, Any]:
    """Drop None / empty values recursively (FHIR forbids empty elements)."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, dict):
            v = _clean(v)
        elif isinstance(v, list):
            v = [_clean(x) if isinstance(x, dict) else x for x in v if x not in (None, "", {}, [])]
            v = [x for x in v if x not in (None, "", {}, [])]
        if v in (None, "", {}, []):
            continue
        out[k] = v
    return out


# ------------------------------------------------------------------ resources

def patient_resource(p: Patient) -> dict[str, Any]:
    identifiers = []
    if p.abha_number:
        identifiers.append({
            "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": "MR", "display": "Medical record number"}], "text": "ABHA Number"},
            "system": ABHA_SYSTEM, "value": p.abha_number,
        })
    if p.abha_address:
        identifiers.append({"type": {"text": "ABHA Address"}, "system": ABHA_ADDRESS_SYSTEM, "value": p.abha_address})
    return _clean({
        "resourceType": "Patient", "id": p.id,
        "meta": {"profile": [NRCES + "Patient"]},
        "identifier": identifiers,
        "name": [{"text": p.name}],
        "telecom": [{"system": "phone", "value": p.phone, "use": "mobile"}] if p.phone else [],
        "gender": p.gender, "birthDate": dt(p.birth_date),
        "communication": [{"language": {"coding": [{"system": "urn:ietf:bcp:47", "code": p.preferred_language}]}}],
    })


def practitioner_resource(name: str, registration: str | None) -> dict[str, Any]:
    return _clean({
        "resourceType": "Practitioner", "id": stable_id("practitioner", name, registration or ""),
        "meta": {"profile": [NRCES + "Practitioner"]},
        "identifier": [{"type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": "MD", "display": "Medical License number"}]},
                        "system": DOCTOR_SYSTEM, "value": registration}] if registration else [],
        "name": [{"text": name}],
    })


def organization_resource(name: str) -> dict[str, Any]:
    return {
        "resourceType": "Organization", "id": stable_id("organization", name),
        "meta": {"profile": [NRCES + "Organization"]},
        "name": name,
    }


def observation_resource(o: Observation) -> dict[str, Any]:
    coding = [{"system": LOINC, "code": o.loinc, "display": o.name}] if o.loinc else []
    value: dict[str, Any] = {}
    if o.value_num is not None and not o.value_text:
        q = {"value": o.value_num, "unit": o.unit}
        if o.unit in UCUM_CODES:
            q.update(system=UCUM, code=UCUM_CODES[o.unit])
        value["valueQuantity"] = q
    elif o.value_text or o.value_original:
        value["valueString"] = o.value_text or o.value_original
    rr = {}
    if o.ref_low is not None:
        rr["low"] = {"value": o.ref_low, "unit": o.unit}
    if o.ref_high is not None:
        rr["high"] = {"value": o.ref_high, "unit": o.unit}
    if o.ref_text:
        rr["text"] = o.ref_text
    return _clean({
        "resourceType": "Observation", "id": o.id,
        "meta": {"profile": [NRCES + ("ObservationVitalSigns" if o.category == "vital-signs" else "Observation")]},
        "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": o.category}]}],
        "code": {"coding": coding, "text": o.name_raw or o.name},
        "subject": ref("Patient", o.patient_id),
        "effectiveDateTime": dt(o.effective_date),
        **value,
        "interpretation": [{"coding": [{"system": INTERP, "code": o.interpretation, "display": INTERP_DISPLAY.get(o.interpretation, o.interpretation)}]}] if o.interpretation else [],
        "referenceRange": [rr] if rr else [],
    })


def medication_request_resource(m: MedicationRequest, practitioner_id: str | None) -> dict[str, Any]:
    when = [w for w, v in (("MORN", m.morning), ("AFT", m.afternoon), ("NIGHT", m.night)) if v]
    per_day = len(when) or {"OD": 1, "BD": 2, "TDS": 3, "QID": 4, "HS": 1, "Q6H": 4, "Q8H": 3, "Q12H": 2}.get(m.frequency_code or "")
    repeat: dict[str, Any] = {}
    if m.frequency_code == "WEEKLY":
        repeat.update(frequency=1, period=1, periodUnit="wk")
    elif per_day:
        repeat.update(frequency=per_day, period=1, periodUnit="d")
    if when and m.frequency_code not in ("SOS", "STAT"):
        repeat["when"] = when
    if m.duration_days:
        repeat["boundsDuration"] = {"value": m.duration_days, "unit": "days", "system": UCUM, "code": "d"}
    meal_text = {"before_food": "Before food", "after_food": "After food", "with_food": "With food",
                 "empty_stomach": "On an empty stomach", "bedtime": "At bedtime"}.get(m.meal_relation or "")
    text_parts = [m.dose, m.frequency_raw, meal_text, f"for {m.duration_days} days" if m.duration_days else m.duration_text, m.instructions]
    dosage = {
        "text": " | ".join(p for p in text_parts if p),
        "additionalInstruction": [{"text": meal_text}] if meal_text else [],
        "timing": {"repeat": repeat, "code": {"text": m.frequency_raw}} if (repeat or m.frequency_raw) else None,
        "asNeededBoolean": True if m.frequency_code == "SOS" else None,
        "route": {"text": m.route} if m.route else None,
    }
    return _clean({
        "resourceType": "MedicationRequest", "id": m.id,
        "meta": {"profile": [NRCES + "MedicationRequest"]},
        "status": m.status, "intent": "order",
        "medicationCodeableConcept": {"text": " ".join(x for x in (m.name, m.strength or "") if x).strip()
                                      + (f" ({m.generic})" if m.generic and m.generic.lower() not in m.name.lower() else "")},
        "subject": ref("Patient", m.patient_id),
        "authoredOn": dt(m.authored_on),
        "requester": ref("Practitioner", practitioner_id) if practitioner_id else ({"display": m.prescriber} if m.prescriber else None),
        "dosageInstruction": [dosage],
    })


def condition_resource(c: Condition) -> dict[str, Any]:
    coding = [{"system": ICD10, "code": c.icd10, "display": c.icd10_display or c.name}] if c.icd10 else []
    return _clean({
        "resourceType": "Condition", "id": c.id,
        "meta": {"profile": [NRCES + "Condition"]},
        "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": c.clinical_status}]},
        "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": c.verification_status}]},
        "code": {"coding": coding, "text": c.name},
        "subject": ref("Patient", c.patient_id),
        "recordedDate": dt(c.recorded_date),
    })


def diagnostic_report_resource(r: DiagnosticReport, observations: list[Observation], performer_org_id: str | None) -> dict[str, Any]:
    is_lab = r.category == "LAB"
    return _clean({
        "resourceType": "DiagnosticReport", "id": r.id,
        "meta": {"profile": [NRCES + ("DiagnosticReportLab" if is_lab else "DiagnosticReportImaging")]},
        "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0074", "code": r.category,
                                  "display": "Laboratory" if is_lab else "Radiology"}]}],
        "code": {"text": r.name or ("Laboratory report" if is_lab else "Imaging report")},
        "subject": ref("Patient", r.patient_id),
        "effectiveDateTime": dt(r.issued),
        "issued": instant(r.issued),
        "performer": [ref("Organization", performer_org_id)] if performer_org_id else [],
        "result": [ref("Observation", o.id) for o in observations],
        "conclusion": r.conclusion,
    })


def encounter_resource(e: Encounter) -> dict[str, Any]:
    names = {"AMB": "ambulatory", "IMP": "inpatient encounter", "EMER": "emergency"}
    return _clean({
        "resourceType": "Encounter", "id": e.id,
        "meta": {"profile": [NRCES + "Encounter"]},
        "status": "finished",
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": e.encounter_class, "display": names.get(e.encounter_class)},
        "subject": ref("Patient", e.patient_id),
        "period": {"start": instant(e.start_date), "end": instant(e.end_date)},
        "reasonCode": [{"text": e.reason}] if e.reason else [],
        "hospitalization": {"dischargeDisposition": {"text": e.discharge_condition}} if e.discharge_condition else None,
    })


def document_reference_resource(d: Document, base_url: str = "") -> dict[str, Any]:
    code, display, _ = COMPOSITION_TYPES.get(d.doc_type or "other", COMPOSITION_TYPES["other"])
    return _clean({
        "resourceType": "DocumentReference", "id": d.id,
        "meta": {"profile": [NRCES + "DocumentReference"]},
        "status": "current", "docStatus": "final",
        "type": {"coding": [{"system": SNOMED, "code": code, "display": display}], "text": d.title or display},
        "subject": ref("Patient", d.patient_id),
        "date": instant(d.created_at),
        "content": [{"attachment": {"contentType": d.mime_type, "title": d.filename, "url": f"{base_url}/api/documents/{d.id}/file",
                                    "creation": instant(d.document_date) if d.document_date else None,
                                    "language": (d.languages or ["en"])[0]}}],
    })


def validate_resource(res: dict[str, Any]) -> list[str]:
    """Validate structure against FHIR R4B models; returns a list of error strings."""
    from fhir.resources.R4B import get_fhir_model_class

    try:
        get_fhir_model_class(res["resourceType"]).parse_obj(res)
        return []
    except Exception as e:  # noqa: BLE001
        return [f"{res.get('resourceType')}/{res.get('id')}: {str(e)[:400]}"]
