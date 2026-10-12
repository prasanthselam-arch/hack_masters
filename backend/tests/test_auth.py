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


def _client(name: str, login: str, password: str = "secret-pass") -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/register", json={"name": name, "login": login, "password": password})
    assert r.status_code == 200, r.text
    return c


def test_login_normalization_and_password_hash():
    assert auth.normalize_login(" Asha@Example.COM ") == "asha@example.com"
    assert auth.normalize_login("+91 98765 43210") == auth.normalize_login("09876543210") == "9876543210"
    for bad in ("12345", "asha@", "5876543210"):
        with pytest.raises(auth.AuthError):
            auth.normalize_login(bad)
    h = auth.hash_password("correct horse")
    assert h.startswith("scrypt$") and "correct horse" not in h
    assert auth.verify_password("correct horse", h) and not auth.verify_password("wrong", h)


def test_register_login_logout(engine):
    c = _client("Asha", "asha@example.com")
    assert c.get("/api/auth/me").json()["name"] == "Asha"
    assert TestClient(app).post("/api/auth/register", json={"name": "X", "login": "ASHA@example.com", "password": "another-pass"}).status_code == 400
    assert TestClient(app).post("/api/auth/register", json={"name": "X", "login": "x@example.com", "password": "short"}).status_code == 400

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
