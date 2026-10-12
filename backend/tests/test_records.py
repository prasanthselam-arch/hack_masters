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


def test_a_finished_course_stops_being_active_without_reconfirming():
    rx = MedicationRequest(patient_id="p", name="Azee", name_raw="Azee", duration_days=5, authored_on=date(2026, 3, 1), status="active")
    assert records.medication_status(rx, today=date(2026, 3, 5)) == "active"
    assert records.medication_status(rx, today=date(2026, 3, 7)) == "completed"
    rx.duration_days = None
    assert records.medication_status(rx, today=date(2027, 1, 1)) == "active"


def test_deleting_a_profile_removes_its_abha_otp_sessions(db):
    from app.models.tables import AbhaSession

    patient = Patient(name="Ravi")
    db.add(patient)
    db.commit()
    db.add(AbhaSession(patient_id=patient.id, otp="123456"))
    db.commit()
    records.delete_patient(db, patient)
    assert db.exec(select(AbhaSession)).all() == []


def test_bound_only_results_are_not_flagged_after_review_edits():
    from app.pipeline.validate import refresh_review
    from app.schemas.review import ReviewObservation

    payload = ReviewPayload(document=ReviewDocument(doc_type="lab_report"), observations=[
        ReviewObservation(name_raw="CRP", name="CRP", value_num=0.5, value_text="<0.5", unit="mg/dL", ref_high=0.3),
        ReviewObservation(name_raw="CRP", name="CRP", value_num=0.5, unit="mg/dL", ref_high=0.3),
    ])
    bound, plain = refresh_review(payload, "male").observations
    assert bound.interpretation is None
    assert plain.interpretation == "H"


def test_deleting_the_newer_prescription_reactivates_the_older_one(db):
    p = Patient(name="Asha")
    db.add(p)
    db.commit()
    old, new = date.today() - timedelta(days=200), date.today() - timedelta(days=10)
    _confirm(db, p, old, [("Glycomet", "Metformin")])
    _confirm(db, p, new, [("Glyciphage", "Metformin")])
    assert _active(db, p) == [("Metformin", new)]
    newer = db.exec(select(Document).where(Document.patient_id == p.id)).all()
    records.delete_document(db, next(d for d in newer if d.document_date == new))
    assert _active(db, p) == [("Metformin", old)]
