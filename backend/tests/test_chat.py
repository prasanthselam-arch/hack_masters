from datetime import date
from types import SimpleNamespace

from sqlmodel import Session, SQLModel, create_engine

from app.models.tables import Document, MedicationRequest, Observation, Patient
from app.services import chat


def test_reply_carries_cited_records_trend_and_follow_ups(monkeypatch):
    eng = create_engine("sqlite://")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as db:
        p = Patient(name="Ramesh")
        db.add(p)
        db.commit()
        old = Observation(patient_id=p.id, name="HbA1c", name_raw="HbA1c", loinc="4548-4", value_num=8.1, unit="%",
                          interpretation="H", effective_date=date(2025, 9, 1))
        new = Observation(patient_id=p.id, name="HbA1c", name_raw="HbA1c", loinc="4548-4", value_num=7.6, unit="%",
                          interpretation="H", effective_date=date(2026, 3, 26))
        med = MedicationRequest(patient_id=p.id, name="Glycomet", name_raw="Glycomet", strength="500 mg", morning=1, night=1)
        db.add_all([old, new, med])
        db.commit()

        answer = chat.ChatAnswer(
            answer="Your **HbA1c** is 7.6 %.\n\n| Medicine | When |\n| --- | --- |\n| Glycomet | 1-0-1 |",
            cited_record_ids=[new.id, med.id, "made-up-id"], answered_from_records=True, suggest_doctor=False,
            follow_up_questions=["How has my HbA1c changed?", " ", "What is Glycomet for?"],
        )
        monkeypatch.setattr(chat.llm, "parse", lambda *a, **k: SimpleNamespace(parsed=answer))
        r = chat.ask(db, p, "how is my sugar?", [])

    assert r["answer"].splitlines()[2:] == ["| Medicine | When |", "| --- | --- |", "| Glycomet | 1-0-1 |"]
    assert [c["id"] for c in r["citations"]] == [new.id, med.id]
    assert [x["id"] for x in r["results"]] == [new.id]
    assert [pt["value"] for pt in r["results"][0]["trend"]] == [8.1, 7.6]
    assert r["medications"][0]["name"] == "Glycomet" and r["medications"][0]["night"] == 1
    assert r["follow_ups"] == ["How has my HbA1c changed?", "What is Glycomet for?"]


def test_results_and_medicines_found_when_only_the_document_is_cited(monkeypatch):
    eng = create_engine("sqlite://")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as db:
        p = Patient(name="Ramesh")
        db.add(p)
        db.commit()
        doc = Document(patient_id=p.id, filename="lab.pdf", mime_type="application/pdf", file_path="lab.pdf", status="confirmed", title="Lipid panel")
        db.add(doc)
        db.commit()
        ldl = Observation(patient_id=p.id, document_id=doc.id, name="LDL Cholesterol", name_raw="LDL", value_num=112.0, unit="mg/dL",
                          interpretation="H", effective_date=date(2026, 3, 26))
        tg = Observation(patient_id=p.id, document_id=doc.id, name="Triglycerides", name_raw="TG", value_num=162.0, unit="mg/dL",
                         interpretation="H", effective_date=date(2026, 3, 26))
        hdl = Observation(patient_id=p.id, document_id=doc.id, name="HDL Cholesterol", name_raw="HDL", value_num=48.0, unit="mg/dL",
                          interpretation="N", effective_date=date(2026, 3, 26))
        old_rx = MedicationRequest(patient_id=p.id, name="Atorva", name_raw="Atorva", strength="10 mg", authored_on=date(2025, 1, 1))
        new_rx = MedicationRequest(patient_id=p.id, name="Atorva", name_raw="Atorva", strength="20 mg", authored_on=date(2026, 2, 3))
        telma = MedicationRequest(patient_id=p.id, name="Telma 40", name_raw="Telma 40", generic="Telmisartan", strength="40 mg",
                                  authored_on=date(2026, 2, 3))
        telma_copy = MedicationRequest(patient_id=p.id, name="Telma", name_raw="Telma", generic="Telmisartan", strength="40mg",
                                       authored_on=date(2026, 2, 3))
        db.add_all([ldl, tg, hdl, old_rx, new_rx, telma, telma_copy])
        db.commit()

        answer = chat.ChatAnswer(
            answer="Your blood fats (162 mg/dL) and **LDL Cholesterol** (112 mg/dL) are high. You take Atorva at night.",
            cited_record_ids=[doc.id, telma.id, telma_copy.id], answered_from_records=True, suggest_doctor=False)
        monkeypatch.setattr(chat.llm, "parse", lambda *a, **k: SimpleNamespace(parsed=answer))
        r = chat.ask(db, p, "how are my lipids?", [])

    assert [x["name"] for x in r["results"]] == ["LDL Cholesterol", "Triglycerides"]
    assert [(m["name"], m["strength"]) for m in r["medications"]] == [("Telma 40", "40 mg"), ("Atorva", "20 mg")]
    assert r["citations"][0]["id"] == doc.id


def test_romanised_telugu_gets_a_telugu_reply_label_and_emergency_notice(monkeypatch):
    eng = create_engine("sqlite://")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as db:
        p = Patient(name="Ramesh")
        db.add(p)
        db.commit()
        answer = chat.ChatAnswer(
            reply_language="Telugu", understood_question="I have chest pain, what should I do?",
            answer="మీకు ఛాతీ నొప్పి ఉంటే వెంటనే 112కు కాల్ చేయండి.", cited_record_ids=[], answered_from_records=False,
            suggest_doctor=True, emergency_symptoms=True)
        monkeypatch.setattr(chat.llm, "parse", lambda *a, **k: SimpleNamespace(parsed=answer))
        r = chat.ask(db, p, "naku chest lo noppi ga undi", [], "en")

    assert r["reply_language"] == "te"
    assert r["understood_question"] == "I have chest pain, what should I do?"
    assert r["emergency_notice"].startswith("మీకు")


def test_reply_language_trusts_the_script_over_the_label():
    assert chat.reply_language("మీ షుగర్ బాగుంది", "hi") == "te"
    assert chat.reply_language("तुमची साखर ठीक आहे", "mr") == "mr"
    assert chat.reply_language("तुम्हारी शुगर ठीक है", "") == "hi"
    assert chat.reply_language("Your sugar is fine", "te") == "en"
    assert chat.reply_language("Tu azúcar está bien", "es") == "es"
    assert chat.reply_language("Your sugar is fine", "") == "en"
