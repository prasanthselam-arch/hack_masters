import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session
from app.main import app
from app.models.tables import Document
from app.services import auth


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)

    def session():
        with Session(eng) as s:
            yield s

    app.dependency_overrides[get_session] = session
    auth._failures.clear()
    yield eng
    app.dependency_overrides.clear()


def _client(name: str, login: str, password: str = "secret-pass", email: str | None = None) -> TestClient:
    c = TestClient(app)
    email = email or (login.lower() if "@" in login else f"{''.join(ch for ch in login if ch.isdigit())}@example.com")
    sent = c.post("/api/auth/register/start", json={"name": name, "login": login, "email": email, "password": password})
    assert sent.status_code == 200, sent.text
    r = c.post("/api/auth/register/verify", json={"email": email, "code": sent.json()["dev_code"]})
    assert r.status_code == 200, r.text
    return c


def test_login_normalization_and_password_hash():
    assert auth.normalize_login(" Asha@Example.COM ") == "asha@example.com"
    assert auth.normalize_login("+91 98765 43210") == auth.normalize_login("09876543210") == "+919876543210"
    assert auth.normalize_login("+44 07911 123456") == "+447911123456"
    for bad in ("12345", "asha@", "5876543210"):
        with pytest.raises(auth.AuthError):
            auth.normalize_login(bad)
    h = auth.hash_password("correct horse")
    assert h.startswith("scrypt$") and "correct horse" not in h
    assert auth.verify_password("correct horse", h) and not auth.verify_password("wrong", h)


def test_register_login_logout(engine):
    c = _client("Asha", "asha@example.com")
    assert c.get("/api/auth/me").json()["name"] == "Asha"
    start = "/api/auth/register/start"
    assert TestClient(app).post(start, json={"name": "X", "login": "ASHA@example.com", "password": "another-pass"}).status_code == 400
    assert TestClient(app).post(start, json={"name": "X", "login": "x@example.com", "password": "short"}).status_code == 400

    c.post("/api/auth/logout")
    assert c.get("/api/auth/me").status_code == 401
    assert c.post("/api/auth/login", json={"login": "asha@example.com", "password": "nope-nope"}).status_code == 401
    assert c.post("/api/auth/login", json={"login": "asha@example.com", "password": "secret-pass"}).status_code == 200
    assert c.get("/api/auth/me").status_code == 200


def test_repeated_failures_are_throttled(engine):
    _client("Ravi", "9876543210")
    c = TestClient(app)
    for _ in range(auth.MAX_FAILURES):
        assert c.post("/api/auth/login", json={"login": "9876543210", "password": "wrong-pass"}).status_code == 401
    r = c.post("/api/auth/login", json={"login": "9876543210", "password": "secret-pass"})
    assert r.status_code == 401 and "Too many" in r.json()["detail"]


def test_records_require_sign_in(engine):
    anon = TestClient(app)
    assert anon.get("/api/patients").status_code == 401
    assert anon.post("/api/patients", json={"name": "Nobody"}).status_code == 401
    assert anon.get("/api/health").status_code == 200


def test_accounts_only_see_their_own_profiles_and_documents(engine):
    asha, ravi = _client("Asha", "asha@example.com"), _client("Ravi", "ravi@example.com")
    pid = asha.post("/api/patients", json={"name": "Asha", "gender": "female"}).json()["id"]
    asha.post("/api/patients", json={"name": "Asha's mother"})
    with Session(engine) as s:
        doc = Document(patient_id=pid, filename="rx.png", mime_type="image/png", file_path="", status="review")
        s.add(doc)
        s.commit()
        did = doc.id

    assert [p["name"] for p in asha.get("/api/patients").json()] == ["Asha", "Asha's mother"]
    assert ravi.get("/api/patients").json() == []
    for path in (f"/api/patients/{pid}", f"/api/patients/{pid}/profile", f"/api/patients/{pid}/documents",
                 f"/api/patients/{pid}/fhir", f"/api/documents/{did}", f"/api/documents/{did}/file"):
        assert ravi.get(path).status_code == 404, path
    assert ravi.delete(f"/api/patients/{pid}").status_code == 404
    assert ravi.post(f"/api/patients/{pid}/abha/init", json={"abha_address": "x.y@abdm"}).status_code == 404
    assert asha.get(f"/api/documents/{did}").status_code == 200


def test_delete_account_removes_profiles(engine):
    c = _client("Asha", "asha@example.com")
    pid = c.post("/api/patients", json={"name": "Asha"}).json()["id"]
    assert c.post("/api/auth/delete-account", json={"password": "wrong-pass"}).status_code == 401
    assert c.post("/api/auth/delete-account", json={"password": "secret-pass"}).json() == {"deleted": True}
    assert c.get("/api/auth/me").status_code == 401
    other = _client("Asha again", "asha@example.com")
    assert other.get(f"/api/patients/{pid}").status_code == 404


def test_profile_validation_relationship_and_account_settings(engine):
    c = _client("Asha", "asha@example.com")
    me = c.post("/api/patients", json={"name": "  Asha   Rao ", "phone": "98765 43210"}).json()
    assert me["name"] == "Asha Rao" and me["phone"] == "+919876543210" and me["relationship"] == "self"
    for bad in ({"name": " "}, {"name": "A", "phone": "12345"}, {"name": "A", "birth_date": "2999-01-01"},
                {"name": "A", "relationship": "neighbour"}, {"name": "A", "gender": "x"}):
        assert c.post("/api/patients", json=bad).status_code == 422, bad
    dad = c.post("/api/patients", json={"name": "Ravi", "relationship": "father", "phone": "+1 415 555 2671"}).json()
    assert dad["relationship"] == "father" and dad["phone"] == "+14155552671"
    r = c.patch(f"/api/patients/{dad['id']}", json={"relationship": "father_in_law", "birth_date": "1960-05-01"})
    assert r.status_code == 200 and r.json()["relationship"] == "father_in_law"
    assert c.patch(f"/api/patients/{dad['id']}", json={"name": None}).status_code == 422

    assert c.patch("/api/auth/me", json={"name": "Asha R"}).json()["name"] == "Asha R"
    assert c.patch("/api/auth/me", json={"login": "+91 91234 56789"}).status_code == 400  # needs the password
    r = c.patch("/api/auth/me", json={"login": "+91 91234 56789", "current_password": "secret-pass"})
    assert r.status_code == 200 and r.json()["login"] == "+919123456789"

    other = TestClient(app)
    other.post("/api/auth/login", json={"login": "9123456789", "password": "secret-pass"}).raise_for_status()
    assert c.post("/api/auth/password", json={"current_password": "wrong", "new_password": "new-secret-1"}).status_code == 400
    assert c.post("/api/auth/password", json={"current_password": "secret-pass", "new_password": "short"}).status_code == 400
    assert c.post("/api/auth/password", json={"current_password": "secret-pass", "new_password": "new-secret-1"}).status_code == 200
    assert c.get("/api/auth/me").status_code == 200          # this device stays signed in
    assert other.get("/api/auth/me").status_code == 401      # other devices are signed out


def test_dashboard_lists_a_drug_from_a_twice_saved_prescription_once(engine):
    from datetime import date

    from app.models.tables import MedicationRequest

    c = _client("Ravi", "ravi@example.com")
    pid = c.post("/api/patients", json={"name": "Ravi"}).json()["id"]
    with Session(engine) as db:
        for strength in ("10 mg", "10mg", "20 mg"):
            db.add(MedicationRequest(patient_id=pid, name="Atorva", name_raw="Atorva", generic="Atorvastatin", strength=strength,
                                     authored_on=date(2026, 2, 3)))
        db.commit()
    prof = c.get(f"/api/patients/{pid}/profile").json()
    assert sorted(m["strength"] for m in prof["active_medications"]) == ["10 mg", "20 mg"]
    assert prof["counts"]["medications"] == 2


def test_main_person_manages_family_but_keeps_their_own_profile(engine):
    c = _client("Hemanth", "+919876543210")
    me = c.post("/api/patients", json={"name": "Hemanth"}).json()
    assert me["relationship"] == "self"
    mother = c.post("/api/patients", json={"name": "Lakshmi", "relationship": "mother"}).json()
    assert c.post("/api/patients", json={"name": "Copy", "relationship": "self"}).status_code == 409

    edited = c.patch(f"/api/patients/{mother['id']}", json={"name": "Lakshmi Devi", "relationship": "grandmother"})
    assert edited.status_code == 200 and edited.json()["relationship"] == "grandmother"
    assert c.patch(f"/api/patients/{mother['id']}", json={"relationship": "self"}).status_code == 409
    assert c.patch(f"/api/patients/{me['id']}", json={"relationship": "father"}).status_code == 409
    assert c.patch(f"/api/patients/{me['id']}", json={"name": "Hemanth S"}).status_code == 200

    assert c.delete(f"/api/patients/{me['id']}").status_code == 409
    assert c.delete(f"/api/patients/{mother['id']}").status_code == 200
    assert [p["name"] for p in c.get("/api/patients").json()] == ["Hemanth S"]
