from datetime import date, datetime, timedelta, timezone

import httpx
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import get_settings
from app.main import app
from app.models.tables import Account, Document, MedicationRequest, Notification, Observation, Patient
from app.services import auth, mailer, notifications
from tests.test_auth import _client, engine  # noqa: F401  (engine is a fixture)

START, VERIFY = "/api/auth/register/start", "/api/auth/register/verify"


def test_sign_up_takes_an_email_and_a_first_and_last_name(engine, local_mail):
    c = TestClient(app)
    body = {"first_name": " Ravi ", "last_name": "Kumar  Reddy", "password": "secret-pass"}
    assert "sign up with your email" in c.post(START, json={**body, "email": "98765 43210"}).json()["detail"]
    assert "last name" in c.post(START, json={**body, "last_name": " ", "email": "ravi@example.com"}).json()["detail"]
    assert "numbers or symbols" in c.post(START, json={**body, "first_name": "R4vi", "email": "ravi@example.com"}).json()["detail"]
    assert c.post(START, json={**body, "first_name": "रवि", "email": "x@example.com"}).status_code == 200  # any script
    sent = c.post(START, json={**body, "email": "Ravi@Example.com"}).json()
    assert sent["sent_to"] == "ravi@example.com" and len(sent["dev_code"]) == 6
    assert local_mail[-1].to == "ravi@example.com" and sent["dev_code"] in local_mail[-1].text
    assert c.get("/api/auth/me").status_code == 401  # nothing is created before the code

    wrong = "000000" if sent["dev_code"] != "000000" else "111111"
    r = c.post(VERIFY, json={"email": "ravi@example.com", "code": wrong})
    assert r.status_code == 400 and "4 tries left" in r.json()["detail"]
    me = c.post(VERIFY, json={"email": "ravi@example.com", "code": sent["dev_code"]}).json()
    assert me["login"] == "ravi@example.com" and me["name"] == "Ravi Kumar Reddy" and me["email_verified"]
    assert c.post(VERIFY, json={"email": "ravi@example.com", "code": sent["dev_code"]}).status_code == 400  # used up

    # switching the sign-in to a mobile number keeps the verified email as another way in, for this account only
    c.patch("/api/auth/me", json={"login": "98765 43210", "current_password": "secret-pass"}).raise_for_status()
    other = TestClient(app)
    assert other.post("/api/auth/login", json={"login": "ravi@example.com", "password": "secret-pass"}).status_code == 200
    assert other.post("/api/auth/login", json={"login": "9876543210", "password": "secret-pass"}).status_code == 200
    assert "already exists" in other.post(START, json={**body, "email": "ravi@example.com"}).json()["detail"]


def test_codes_expire_and_resending_is_rate_limited(engine, monkeypatch):
    from app.services import codes

    c = TestClient(app)
    body = {"first_name": "Asha", "last_name": "Rao", "email": "asha@example.com", "password": "secret-pass"}
    first = c.post(START, json=body).json()["dev_code"]
    second = c.post(START, json=body).json()["dev_code"]
    if first != second:
        assert c.post(VERIFY, json={"email": "asha@example.com", "code": first}).status_code == 400  # replaced
    monkeypatch.setattr(codes, "RESEND_AFTER", timedelta(seconds=60))
    assert "Please wait" in c.post(START, json=body).json()["detail"]
    with Session(engine) as db:  # the wait is per kind of code: a reset right after signing up still works
        assert codes.issue(db, "asha@example.com", "reset")["dev_code"]
    monkeypatch.setattr(codes, "RESEND_AFTER", timedelta(0))
    for _ in range(codes.MAX_PER_HOUR - 2):
        c.post(START, json=body)
    assert "Too many codes" in c.post(START, json=body).json()["detail"]

    with Session(engine) as db:
        rows = db.exec(select(codes.EmailCode)).all()
        for row in rows:
            row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.add(row)
        db.commit()
    latest = c.post("/api/auth/register/verify", json={"email": "asha@example.com", "code": "123456"})
    assert "expired" in latest.json()["detail"]


def test_forgot_password_resets_with_an_email_code(engine, local_mail):
    c = _client("Asha", "asha@example.com")
    phone = TestClient(app)
    phone.post("/api/auth/login", json={"login": "asha@example.com", "password": "secret-pass"}).raise_for_status()

    anon = TestClient(app)
    unknown = anon.post("/api/auth/forgot", json={"login": "nobody@example.com"}).json()
    assert unknown["sent"] and "dev_code" not in unknown  # same answer, no hint whether the account exists
    code = anon.post("/api/auth/forgot", json={"login": "ASHA@example.com"}).json()["dev_code"]
    assert "password reset" in local_mail[-1].subject

    bad = anon.post("/api/auth/reset", json={"login": "asha@example.com", "code": code, "password": "short"})
    assert bad.status_code == 400 and "8 characters" in bad.json()["detail"]
    r = anon.post("/api/auth/reset", json={"login": "asha@example.com", "code": code, "password": "brand-new-pass"})
    assert r.status_code == 200 and anon.get("/api/auth/me").status_code == 200
    assert c.get("/api/auth/me").status_code == 401 and phone.get("/api/auth/me").status_code == 401
    assert "was reset" in local_mail[-1].subject
    assert TestClient(app).post("/api/auth/login", json={"login": "asha@example.com", "password": "brand-new-pass"}).status_code == 200


def test_accounts_without_an_email_can_add_and_change_one(engine, local_mail):
    with Session(engine) as db:  # an account from before emails were required
        db.add(Account(login="+919876543210", name="Hemanth", password_hash=auth.hash_password("secret-pass")))
        db.commit()
    c = TestClient(app)
    me = c.post("/api/auth/login", json={"login": "9876543210", "password": "secret-pass"}).json()
    assert me["email"] is None and not me["email_verified"]
    assert c.post("/api/auth/forgot", json={"login": "9876543210"}).json().get("dev_code") is None
    assert not local_mail  # no sign-in alert without a verified email

    code = c.post("/api/auth/email/start", json={"email": "hemanth@example.com"}).json()["dev_code"]
    me = c.post("/api/auth/email/verify", json={"code": code}).json()
    assert me["email"] == "hemanth@example.com" and me["email_verified"]

    assert "current password" in c.post("/api/auth/email/start", json={"email": "new@example.com"}).json()["detail"]
    code = c.post("/api/auth/email/start", json={"email": "new@example.com", "current_password": "secret-pass"}).json()["dev_code"]
    c.post("/api/auth/email/verify", json={"code": code}).raise_for_status()
    alert = local_mail[-1]
    assert alert.to == "hemanth@example.com" and "new@example.com" in alert.text  # the old address is told

    off = c.patch("/api/auth/me", json={"notify_security": False, "notify_weekly": False}).json()["notify"]
    assert off == {"security": False, "medicines": True, "weekly": False}
    count = len(local_mail)
    TestClient(app).post("/api/auth/login", json={"login": "new@example.com", "password": "secret-pass"}).raise_for_status()
    assert len(local_mail) == count  # security alerts turned off


def test_sign_in_alert_names_the_device(engine, local_mail):
    _client("Asha", "asha@example.com")
    ua = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/130.0 Mobile Safari/537.36"
    TestClient(app, headers={"user-agent": ua}).post("/api/auth/login", json={"login": "asha@example.com", "password": "secret-pass"})
    assert local_mail[-1].subject == "New sign-in to Health Copilot" and "Chrome on Android" in local_mail[-1].text


def test_production_without_an_email_provider_refuses_instead_of_leaking_codes(engine, monkeypatch):
    monkeypatch.setattr(get_settings(), "cookie_secure", True)
    r = TestClient(app).post(START, json={"first_name": "Asha", "last_name": "Rao", "email": "asha@example.com", "password": "secret-pass"})
    assert r.status_code == 503 and "dev_code" not in r.text


def test_google_apps_script_request(monkeypatch):
    import json

    import pytest

    s = get_settings()
    url = "https://script.google.com/macros/s/abc/exec"
    monkeypatch.setattr(s, "google_script_url", url)
    monkeypatch.setattr(s, "google_script_secret", "relay-secret")
    seen, answer = [], {"ok": True, "remaining": 99}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.method == "POST":  # Apps Script runs doPost, then redirects to its output
            return httpx.Response(302, headers={"location": "https://script.googleusercontent.com/macros/echo?x=1"})
        return httpx.Response(200, json=answer)

    real = httpx.Client
    monkeypatch.setattr(mailer.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), follow_redirects=True))
    mailer.send("asha@example.com", "Hello", ["Line <b>one</b>"], code="123456")
    body = json.loads(seen[0].content)
    assert str(seen[0].url) == url and seen[1].method == "GET"
    assert body["secret"] == "relay-secret" and body["to"] == "asha@example.com" and body["name"] == "Health Copilot"
    assert "123456" in body["html"] and "123456" in body["text"]
    assert "&lt;b&gt;" in body["html"]  # text is escaped
    assert not mailer.outbox

    answer = {"ok": False, "error": "forbidden"}
    with pytest.raises(mailer.MailError):
        mailer.send("asha@example.com", "Hello", ["Hi"])


def test_daily_job_sends_medicine_reminders_once_and_weekly_summaries(engine, local_mail, monkeypatch):
    now = datetime(2026, 10, 12, 3, 30, tzinfo=timezone.utc)  # 9 AM IST
    with Session(engine) as db:
        acc = Account(login="asha@example.com", name="Asha", password_hash="x", email="asha@example.com",
                      email_verified_at=now - timedelta(days=30), created_at=now - timedelta(days=30))
        quiet = Account(login="ravi@example.com", name="Ravi", password_hash="x", email="ravi@example.com",
                        email_verified_at=now, created_at=now - timedelta(days=30), notify_medicines=False, notify_weekly=False)
        db.add_all([acc, quiet])
        db.commit()
        for owner in (acc, quiet):
            p = Patient(owner_id=owner.id, name=f"{owner.name}'s mother", relationship="mother")
            db.add(p)
            db.commit()
            doc = Document(patient_id=p.id, filename="r.pdf", mime_type="application/pdf", file_path="", status="confirmed",
                           confirmed_at=now - timedelta(days=2))
            db.add(doc)
            db.commit()
            db.add(Observation(patient_id=p.id, document_id=doc.id, name_raw="HbA1c", name="HbA1c", value_num=7.8, unit="%",
                               interpretation="H"))
            db.add(MedicationRequest(patient_id=p.id, name="Azithral", name_raw="Azithral", strength="500 mg",
                                     duration_days=5, authored_on=date(2026, 10, 8)))  # last day 12 Oct
            db.add(MedicationRequest(patient_id=p.id, name="Metformin", name_raw="Metformin", authored_on=date(2026, 9, 1)))
        db.commit()

        assert notifications.run_daily(db, now) == {"medicines": 1, "weekly": 1, "failed": 0}
        reminder, weekly = [m for m in local_mail if m.to == "asha@example.com"]
        assert "Azithral 500 mg, a 5-day course, ends today" in reminder.text and "doctor" in reminder.text
        assert "1 new record" in weekly.text and "HbA1c 7.8 % (high)" in weekly.text and "2 active medicines" in weekly.text
        assert all(m.to != "ravi@example.com" for m in local_mail)

        assert notifications.run_daily(db, now + timedelta(days=1)) == {"medicines": 0, "weekly": 0, "failed": 0}
        assert len(db.exec(select(Notification)).all()) == 1
        assert notifications.run_daily(db, now + timedelta(days=7))["weekly"] == 1

    monkeypatch.setattr(get_settings(), "cron_secret", "")
    assert TestClient(app).post("/api/internal/notifications/run").status_code == 404
    monkeypatch.setattr(get_settings(), "cron_secret", "s3cret")
    assert TestClient(app).post("/api/internal/notifications/run", headers={"x-cron-secret": "nope"}).status_code == 404
    assert TestClient(app).post("/api/internal/notifications/run", headers={"x-cron-secret": "s3cret"}).status_code == 200
