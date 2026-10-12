import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.tables import Document, MedicationRequest, Observation, Patient
from app.services import abha_mock


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_link_and_import(db):
    p = Patient(name="Ravi Kumar", gender="male")
    db.add(p)
    db.commit()
    with pytest.raises(ValueError):
        abha_mock.init_link(db, p, "1234", None)
    init = abha_mock.init_link(db, p, "91123456789012", None)
    with pytest.raises(ValueError):
        abha_mock.confirm_link(db, p, init["txn_id"], "000000")
    res = abha_mock.confirm_link(db, p, init["txn_id"], init["demo_otp_hint"])
    assert res["abha_number"] == "91-1234-5678-9012"

    out = abha_mock.import_from_hip(db, p, ["Prescription", "DiagnosticReport", "DischargeSummary"])
    assert out["fhir_validation_errors"] == []
    assert len(out["imported"]) == 4
    docs = db.exec(select(Document).where(Document.patient_id == p.id)).all()
    assert all(d.status == "confirmed" and d.source == "abdm_import" for d in docs)
    a1c = db.exec(select(Observation).where(Observation.loinc == "4548-4")).all()
    assert sorted(o.value_num for o in a1c) == [7.6, 8.1]
    assert all(o.interpretation == "H" for o in a1c)
    vitd = db.exec(select(Observation).where(Observation.loinc == "62292-8")).one()
    assert vitd.interpretation == "L"
    meds = db.exec(select(MedicationRequest).where(MedicationRequest.patient_id == p.id)).all()
    assert {m.generic for m in meds if m.status == "active"} >= {"Metformin", "Atorvastatin"}

    # re-import is idempotent
    abha_mock.import_from_hip(db, p, ["DiagnosticReport"])
    assert len(db.exec(select(Observation).where(Observation.loinc == "4548-4")).all()) == 2
