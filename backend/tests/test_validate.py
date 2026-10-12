from app.pipeline.validate import build_review, parse_date, parse_number, parse_range
from app.schemas.extraction import (
    DocumentExtraction,
    ExtractedDiagnosis,
    ExtractedMedication,
    ExtractedPatient,
    ExtractedTest,
)


def _test(name, value, unit, ref=None, flag=None, conf=0.97, numeric="auto"):
    num, _ = parse_number(value)
    lo, hi = parse_range(ref)
    return ExtractedTest(
        category="laboratory", panel=None, test_name_as_written=name, test_name=name, value_as_written=value,
        value_numeric=num if numeric == "auto" else numeric, unit=unit, reference_range_as_written=ref,
        ref_low=lo, ref_high=hi, flag_on_report=flag, confidence=conf, page=1,
    )


def _med(name, strength=None, freq=None, duration=None, conf=0.95, **kw):
    return ExtractedMedication(
        name_as_written=name, name=name, generic_name=kw.get("generic"), strength=strength, form=kw.get("form", "tablet"),
        dose=None, frequency_as_written=freq, morning=None, afternoon=None, night=None, meal_relation=None, route=None,
        duration_as_written=duration, duration_days=None, instructions=kw.get("instructions"), confidence=conf, page=1,
    )


def _doc(tests=(), meds=(), dx=(), date="2026-02-03", date_raw="03/02/2026", gender="male"):
    return DocumentExtraction(
        document_type="lab_report", document_date_as_written=date_raw, document_date=date, facility_name="Lab",
        doctor_name=None, doctor_registration=None,
        patient=ExtractedPatient(name="X", age="45 Y", gender=gender, patient_identifier=None, abha_number=None),
        diagnoses=list(dx), medications=list(meds), tests=list(tests), encounter=None, findings=None, impression=None,
        advice=[], follow_up=None, unreadable=[], legibility="good",
    )


def test_parse_helpers():
    assert parse_number("1,50,000") == (150000.0, None)
    assert parse_number("<0.5") == (0.5, "<")
    assert parse_number("Positive") == (None, None)
    assert parse_range("13.0 - 17.0") == (13.0, 17.0)
    assert parse_range("< 200") == (None, 200.0)
    assert parse_range("Up to 5.7") == (None, 5.7)
    assert parse_range(">40") == (40.0, None)


def test_dates_dayfirst():
    issues = []
    assert parse_date(None, "03/02/2026", issues, "d") == "2026-02-03"
    issues = []
    # model wrongly read month-first; verbatim DD/MM text wins
    assert parse_date("2026-03-02", "03/02/2026", issues, "d") == "2026-02-03"
    assert issues and issues[0].code == "date_mismatch"


def test_lab_flags_and_units():
    p = build_review(_doc(tests=[
        _test("Haemoglobin", "10.2", "g/dL", "13.0 - 17.0"),
        _test("Total WBC Count", "7800", "cells/cumm", "4000 - 11000"),
        _test("Platelet Count", "1.2", "lakhs/cumm", "1.5 - 4.1"),
        _test("Potassium", "6.9", "mmol/L", "3.5 - 5.1"),
        _test("HbA1c", "7.4", "%", None),
    ]), None, None)
    hb, wbc, plt, k, a1c = p.observations
    assert hb.loinc == "718-7" and hb.interpretation == "L" and hb.ref_source == "report"
    assert wbc.value_num == 7.8 and wbc.unit == "10^3/uL" and wbc.interpretation == "N"
    assert wbc.ref_low == 4.0 and wbc.ref_high == 11.0
    assert plt.value_num == 120 and plt.interpretation == "L"
    assert k.interpretation == "HH" and k.critical
    assert a1c.interpretation == "H" and a1c.ref_source == "curated"


def test_implausible_value_is_flagged():
    p = build_review(_doc(tests=[_test("Haemoglobin", "112", "g/dL", "13.0 - 17.0")]), None, None)
    o = p.observations[0]
    assert o.needs_review and any(i.code == "implausible" for i in o.issues)


def test_numeric_drift_uses_printed_value():
    p = build_review(_doc(tests=[_test("Serum Creatinine", "1.8", "mg/dL", "0.7 - 1.3", numeric=18.0)]), None, None)
    o = p.observations[0]
    assert o.value_num == 1.8 and any(i.code == "value_mismatch" for i in o.issues)


def test_flag_mismatch():
    p = build_review(_doc(tests=[_test("SGPT", "35", "U/L", "7 - 55", flag="H")]), None, None)
    assert any(i.code == "flag_mismatch" for i in p.observations[0].issues)


def test_bp_split():
    t = _test("Blood Pressure", "150/95", "mmHg")
    t = t.model_copy(update={"category": "vital-signs"})
    p = build_review(_doc(tests=[t]), None, None)
    names = [o.name for o in p.observations]
    assert names == ["Systolic Blood Pressure", "Diastolic Blood Pressure"]
    assert p.observations[0].interpretation == "H"


def test_medications():
    p = build_review(_doc(meds=[
        _med("Dolo 650", freq="1-1-1", duration="x 5 days"),
        _med("Telma", "40 mg", "1-0-0", "1 month"),
        _med("Amlodipine", "50 mg", "OD"),
        _med("Thyronorm", "50 mcg", "1-0-0", instructions="empty stomach"),
    ]), None, None)
    dolo, telma, amlo, thy = p.medications
    assert dolo.generic == "Paracetamol" and dolo.strength == "650 mg" and dolo.frequency_code == "TDS"
    assert dolo.name == "Dolo"
    assert dolo.duration_days == 5
    assert telma.generic == "Telmisartan" and telma.duration_days == 30 and telma.morning == 1
    assert amlo.needs_review and any(i.code == "unusual_strength" for i in amlo.issues)
    assert thy.meal_relation == "empty_stomach"


def test_conditions_icd():
    dx = [ExtractedDiagnosis(text_as_written="T2DM", name="Type 2 diabetes mellitus", icd10=None, status="confirmed", confidence=0.95, page=1),
          ExtractedDiagnosis(text_as_written="HTN", name="Hypertension", icd10="I10", status="history", confidence=0.95, page=1)]
    p = build_review(_doc(dx=dx), None, None)
    assert [c.icd10 for c in p.conditions] == ["E11.9", "I10"]


def test_verifier_rewording_is_not_treated_as_new_item():
    from app.schemas.extraction import VerificationResult

    first = _doc(
        tests=[_test("Haematocrit", "34.2", "%", "36 - 46"), _test("Mean Corpuscular Volume", "78", "fL", "83 - 101")],
        meds=[_med("Uprise-D3", "60000 IU", "once weekly")],
        dx=[ExtractedDiagnosis(text_as_written="IDA", name="Iron deficiency anaemia", icd10=None, status="confirmed", confidence=0.95, page=1)],
    )
    second = _doc(
        tests=[_test("Hematocrit (PCV)", "34.2", "%", "36 - 46"), _test("MCV", "78", "fL", "83 - 101"), _test("RDW", "16.1", "%", "11.6 - 14.0")],
        meds=[_med("Uprise D3 60K", "60000 IU", "once weekly")],
        dx=[ExtractedDiagnosis(text_as_written="IDA", name="Iron deficiency anemia", icd10="D50.9", status="confirmed", confidence=0.95, page=1)],
    )
    vr = VerificationResult(corrected=second, corrections=[], items_added=["RDW"], items_removed=[], uncertain_fields=[])
    p = build_review(second, None, "female", first, vr)
    assert [o.verified for o in p.observations] == ["agreed", "agreed", "added"]
    assert p.medications[0].verified == "agreed"
    assert p.conditions[0].verified == "agreed"


def test_values_printed_with_a_flag_or_unit_keep_their_number():
    assert parse_number("12.5 L") == (12.5, None)
    assert parse_number("12.5 g/dL") == (12.5, None)
    assert parse_number("142 (H)") == (142.0, None)
    assert parse_number("2-3 /hpf") == (None, None)
    assert parse_number("120/80") == (None, None)


def test_banded_and_sex_specific_ranges_pick_the_right_band():
    assert parse_range("Desirable <200 Borderline 200-239 High >=240") == (None, 200.0)
    assert parse_range("Normal <100 Prediabetes 100-125 Diabetes >=126") == (None, 100.0)
    assert parse_range("Deficient <20 Insufficient 20-30 Sufficient 30-100") == (30.0, 100.0)
    assert parse_range("Male 13-17 Female 12-15", "female") == (12.0, 15.0)
    assert parse_range("Male: 13-17 g/dL, Female: 12-15 g/dL", "male") == (13.0, 17.0)
    assert parse_range("Male 13-17 Female 12-15") == (None, None)
    assert parse_range("4.0 - 11.0 x10^3/uL") == (4.0, 11.0)


def test_banded_ranges_do_not_flag_normal_results_low():
    obs = build_review(_doc(tests=[_test("Total Cholesterol", "180", "mg/dL", "Desirable <200 Borderline 200-239")]), None, "male").observations[0]
    assert obs.interpretation == "N"
    hb = build_review(_doc(tests=[_test("Hemoglobin", "12.8", "g/dL", "Male 13-17 Female 12-15")], gender="female"), None, "female").observations[0]
    assert hb.interpretation == "N"


def test_iso_style_written_dates_are_not_read_day_first():
    issues = []
    assert parse_date("2026-03-02", "2026-03-02", issues, "d") == "2026-03-02"
    assert not issues
    assert parse_date("2026-02-03", "03/02/2026", [], "d") == "2026-02-03"
