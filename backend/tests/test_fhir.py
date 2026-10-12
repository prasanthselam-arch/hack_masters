from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.fhir.bundle import bundle_to_extractions, document_bundle, patient_bundle, validate_bundle
from app.models.tables import Document, Patient
from app.pipeline.validate import build_review
from app.services.records import confirm
from tests.test_validate import _doc, _med, _test


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _confirmed_doc(db, ex, doc_type="lab_report"):
    p = Patient(name="Asha Rao", gender="female", abha_number="91-1234-5678-9012", abha_address="asha@abdm")
    db.add(p)
    db.commit()
    d = Document(patient_id=p.id, filename="x.png", mime_type="image/png", file_path="/tmp/x.png", doc_type=doc_type)
    db.add(d)
    db.commit()
    payload = build_review(ex, None, "female")
    payload.document.doc_type = doc_type
    stats = confirm(db, d, payload)
    return p, d, stats


def test_lab_bundle_valid_and_roundtrip(db):
    ex = _doc(tests=[
        _test("Haemoglobin", "10.2", "g/dL", "12.0 - 15.5"),
        _test("HbA1c", "7.4", "%", "4.0 - 5.6"),
    ])
    p, d, stats = _confirmed_doc(db, ex)
    assert stats["fhir_errors"] == 0
    b = document_bundle(db, d)
    assert b["type"] == "document" and b["entry"][0]["resource"]["resourceType"] == "Composition"
    assert validate_bundle(b) == []
    types = {e["resource"]["resourceType"] for e in b["entry"]}
    assert {"Patient", "Observation", "DiagnosticReport", "DocumentReference"} <= types
    patient = next(e["resource"] for e in b["entry"] if e["resource"]["resourceType"] == "Patient")
    assert patient["identifier"][0]["value"] == "91-1234-5678-9012"

    (back, _meta), = bundle_to_extractions(b)
    assert back.document_date == "2026-02-03"
    names = sorted(t.test_name for t in back.tests)
    assert names == ["HbA1c", "Hemoglobin"]
    re_review = build_review(back, None, "female")
    assert {o.loinc: o.interpretation for o in re_review.observations} == {"718-7": "L", "4548-4": "H"}


def test_prescription_bundle(db):
    ex = _doc(meds=[_med("Glycomet", "500 mg", "1-0-1", "x 30 days")])
    ex = ex.model_copy(update={"document_type": "prescription", "doctor_name": "Dr. A. Sharma", "doctor_registration": "KMC 45678"})
    p, d, stats = _confirmed_doc(db, ex, "prescription")
    b = document_bundle(db, d)
    assert validate_bundle(b) == []
    mr = next(e["resource"] for e in b["entry"] if e["resource"]["resourceType"] == "MedicationRequest")
    rep = mr["dosageInstruction"][0]["timing"]["repeat"]
    assert rep["frequency"] == 2 and rep["when"] == ["MORN", "NIGHT"] and rep["boundsDuration"]["value"] == 30
    (back, _), = bundle_to_extractions(b)
    assert back.medications[0].name == "Glycomet" and back.medications[0].duration_days == 30
    assert back.doctor_name == "Dr. A. Sharma"
    pb = patient_bundle(db, p)
    assert pb["type"] == "collection" and validate_bundle(pb) == []
    assert date.fromisoformat(back.document_date)
