"""One-time email codes for sign-up, password reset and adding an email."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlmodel import Session, col, select

from app.config import get_settings
from app.models.tables import EmailCode
from app.services import mailer

TTL = timedelta(minutes=10)
RESEND_AFTER = timedelta(seconds=60)
MAX_PER_HOUR = 5
MAX_ATTEMPTS = 5

SUBJECTS = {"signup": "Your Health Copilot sign-up code", "reset": "Your Health Copilot password reset code",
            "email": "Confirm your email for Health Copilot"}
INTROS = {
    "signup": "Use this code to finish creating your Health Copilot account.",
    "reset": "Use this code to set a new password for your Health Copilot account.",
    "email": "Use this code to confirm this email address for your Health Copilot account.",
}


class CodeError(ValueError):
    pass


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _hash(row_id: str, code: str) -> str:
    return hashlib.sha256(f"{row_id}:{code}".encode()).hexdigest()


def issue(db: Session, email: str, purpose: str, *, account_id: str | None = None,
          payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Email a new code. Returns what the client needs to show (and the code itself on local test servers)."""
    now = datetime.now(timezone.utc)
    for old in db.exec(select(EmailCode).where(EmailCode.created_at < now - timedelta(days=1))).all():
        db.delete(old)
    recent = db.exec(select(EmailCode).where(EmailCode.email == email, EmailCode.created_at > now - timedelta(hours=1))
                     .order_by(col(EmailCode.created_at).desc())).all()
    same = [r for r in recent if r.purpose == purpose]
    if same and (wait := RESEND_AFTER - (now - _utc(same[0].created_at))) > timedelta(0):
        raise CodeError(f"Please wait {int(wait.total_seconds()) + 1} seconds before asking for another code")
    if len(recent) >= MAX_PER_HOUR:
        raise CodeError("Too many codes were requested for this email. Please try again in an hour")
    for r in recent:
        if r.purpose == purpose and not r.used:
            r.used = True
            db.add(r)

    code = f"{secrets.randbelow(10**6):06d}"
    row = EmailCode(email=email, purpose=purpose, account_id=account_id, payload=payload, code_hash="",
                    created_at=now, expires_at=now + TTL)
    row.code_hash = _hash(row.id, code)
    mailer.send(email, SUBJECTS[purpose], [INTROS[purpose], f"It expires in {int(TTL.total_seconds() // 60)} minutes."],
                code=code, footer="If you didn't ask for this, you can ignore this email. Never share this code with anyone.")
    db.add(row)
    db.commit()
    out: dict[str, Any] = {"sent_to": email, "expires_in": int(TTL.total_seconds()), "resend_in": int(RESEND_AFTER.total_seconds())}
    if get_settings().mail_debug:
        out["dev_code"] = code
    return out


def check(db: Session, email: str, purpose: str, code: str, account_id: str | None = None) -> EmailCode:
    """Use up a code. Raises CodeError if it is wrong, expired or tried too often."""
    q = select(EmailCode).where(EmailCode.email == email, EmailCode.purpose == purpose, EmailCode.used == False)  # noqa: E712
    if account_id:
        q = q.where(EmailCode.account_id == account_id)
    row = db.exec(q.order_by(col(EmailCode.created_at).desc())).first()
    if not row or _utc(row.expires_at) < datetime.now(timezone.utc):
        raise CodeError("This code has expired. Please ask for a new one")
    if row.attempts >= MAX_ATTEMPTS:
        raise CodeError("Too many wrong codes. Please ask for a new one")
    if not hmac.compare_digest(row.code_hash, _hash(row.id, "".join(ch for ch in code if ch.isdigit()))):
        row.attempts += 1
        db.add(row)
        db.commit()
        left = MAX_ATTEMPTS - row.attempts
        raise CodeError("That code isn't right. " + (f"{left} tries left" if left else "Please ask for a new one"))
    row.used = True
    db.add(row)
    db.commit()
    return row


def latest_email(db: Session, purpose: str, account_id: str) -> str | None:
    row = db.exec(select(EmailCode).where(EmailCode.purpose == purpose, EmailCode.account_id == account_id,
                                          EmailCode.used == False)  # noqa: E712
                  .order_by(col(EmailCode.created_at).desc())).first()
    return row.email if row else None
