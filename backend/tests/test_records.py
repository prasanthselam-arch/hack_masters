from datetime import date, timedelta

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.tables import Document, MedicationRequest, Patient
from app.schemas.review import ReviewDocument, ReviewMedication, ReviewPayload
from app.services import records


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _confirm(db, patient, when: date, meds: list[tuple[str, str]]):
    doc = Document(patient_id=patient.id, filename="rx.png", mime_type="image/png", file_path="", status="review")
    db.add(doc)
    db.commit()
    payload = ReviewPayload(
        document=ReviewDocument(doc_type="prescription", document_date=when.isoformat()),
        medications=[ReviewMedication(name_raw=n, name=n, generic=g, frequency_code="BD", morning=1, night=1) for n, g in meds],
    )
    records.confirm(db, doc, payload)
    return doc


def _active(db, patient):
    rows = db.exec(select(MedicationRequest).where(MedicationRequest.patient_id == patient.id)).all()
    return sorted((m.generic, m.authored_on) for m in rows if m.status == "active")


@pytest.mark.parametrize("newer_first", [False, True])
def test_only_latest_prescription_of_a_drug_stays_active(db, newer_first):
    p = Patient(name="Asha")
    db.add(p)
    db.commit()
    old, new = date.today() - timedelta(days=200), date.today() - timedelta(days=10)
    batches = [(old, [("Glycomet", "Metformin"), ("Atorva", "Atorvastatin")]), (new, [("Glyciphage", "Metformin")])]
    for when, meds in reversed(batches) if newer_first else batches:
        _confirm(db, p, when, meds)
    assert _active(db, p) == [("Atorvastatin", old), ("Metformin", new)]
