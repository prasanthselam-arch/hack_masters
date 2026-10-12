import pytest

from app.knowledge import dosage, drugs, icd10, labs, norm_unit


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("cells/cumm", "/ul"),
        ("/cu.mm", "/ul"),
        ("Lakhs/cumm", "lakh/ul"),
        ("10^3/µL", "10^3/ul"),
        ("x10³/µL", "10^3/ul"),
        ("Thou/mm3", "10^3/ul"),
        ("million/cumm", "10^6/ul"),
        ("gm%", "g/dl"),
        ("mg%", "mg/dl"),
        ("µIU/mL", "uiu/ml"),
        ("mIU/L", "uiu/ml"),
        ("mm/hr", "mm/h"),
        ("°F", "degf"),
    ],
)
def test_norm_unit(raw, expected):
    assert norm_unit(raw) == expected


def test_lab_match_aliases():
    cat = labs()
    assert cat.match("Haemoglobin (Hb)")[0].loinc == "718-7"
    assert cat.match("SGPT")[0].key == "alt"
    assert cat.match("TLC")[0].key == "wbc"
    assert cat.match("Glycosylated Haemoglobin")[0].key == "hba1c"
    assert cat.match("Serum Creatinine")[0].key == "creatinine"
    assert cat.match("Fasting Blood Sugar")[0].key == "glucose_fasting"
    assert cat.match("HbA1c (Glycated Haemoglobin)") == (cat.tests["hba1c"], 1.0)
    assert cat.match("Totally unknown analyte")[0] is None
    assert cat.match("Totally (unknown) analyte")[0] is None


def test_lab_conversions():
    cat = labs()
    wbc = cat.tests["wbc"]
    assert wbc.convert(7800, "cells/cumm") == (pytest.approx(7.8), True)
    plt = cat.tests["platelets"]
    assert plt.convert(1.5, "lakhs/cumm")[0] == pytest.approx(150)
    glu = cat.tests["glucose_fasting"]
    assert glu.convert(7.0, "mmol/L")[0] == pytest.approx(126.1, rel=1e-3)
    a1c = cat.tests["hba1c"]
    assert a1c.convert(48, "mmol/mol")[0] == pytest.approx(6.54, abs=0.02)
    assert glu.convert(100, "furlongs") is None


def test_sex_specific_range():
    hb = labs().tests["hemoglobin"]
    assert hb.ref_range("male") == (13.0, 17.0)
    assert hb.ref_range("female") == (12.0, 15.5)
    assert hb.ref_range(None) == (12.0, 17.0)


@pytest.mark.parametrize(
    "text,code,m,a,n",
    [
        ("1-0-1", "BD", 1, 0, 1),
        ("1-1-1", "TDS", 1, 1, 1),
        ("0-0-1", "HS", 0, 0, 1),
        ("1-0-0", "OD", 1, 0, 0),
        ("½-0-½", "BD", 0.5, 0, 0.5),
        ("BD", "BD", 1, 0, 1),
        ("T.D.S.", "TDS", 1, 1, 1),
        ("once daily", "OD", 1, 0, 0),
        ("सुबह-शाम", "BD", 1, 0, 1),
    ],
)
def test_parse_frequency(text, code, m, a, n):
    f = dosage().parse_frequency(text)
    assert f["code"] == code
    assert (f["morning"], f["afternoon"], f["night"]) == (m, a, n)


def test_parse_sos():
    assert dosage().parse_frequency("SOS")["code"] == "SOS"


@pytest.mark.parametrize(
    "text,days",
    [("x 5 days", 5), ("5/7", 5), ("1 month", 30), ("2 wks", 14), ("10 दिन", 10), ("for 3 weeks", 21)],
)
def test_duration(text, days):
    assert dosage().parse_duration_days(text) == days


def test_meal_relation():
    d = dosage()
    assert d.parse_meal("after food") == "after_food"
    assert d.parse_meal("खाने के बाद") == "after_food"
    assert d.parse_meal("A.C.") == "before_food"
    assert d.parse_meal("ఖాళీ కడుపుతో") == "empty_stomach"


def test_drug_match():
    dd = drugs()
    d, score, _ = dd.match("Tab. Dolo 650")
    assert d.generic == "Paracetamol" and score >= 0.95
    d, _, _ = dd.match("Telma 40")
    assert d.generic == "Telmisartan"
    d, score, _ = dd.match("Glycomet")
    assert d.generic == "Metformin"
    d, score, _ = dd.match("Pantoprazol")  # misspelt
    assert d is not None and d.generic == "Pantoprazole"
    d, _, _ = dd.match("Xyzzyquil")
    assert d is None


@pytest.mark.parametrize("written, generic", [
    ("Tab Glycomet GP 1", "Metformin + Glimepiride"),
    ("Glycomet-GP 2", "Metformin + Glimepiride"),
    ("Zerodol SP", "Aceclofenac + Paracetamol + Serratiopeptidase"),
    ("Montair LC", "Montelukast + Levocetirizine"),
    ("Glycomet 500", "Metformin"),
])
def test_combination_brands_are_not_collapsed(written, generic):
    d, _, _ = drugs().match(written)
    assert d is not None and d.generic == generic


def test_icd10():
    m = icd10()
    assert m.match("T2DM")[0]["code"] == "E11.9"
    assert m.match("K/C/O HTN")[0]["code"] == "I10"
    assert m.match("Hypothyroidism")[0]["code"] == "E03.9"
