"""Accounts and sessions: scrypt password hashes, opaque session tokens stored only as hashes."""

import base64
import hashlib
import hmac
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.config import get_settings
from app.models.tables import Account, AuthSession
from app.services import contact

COOKIE = "hc_session"
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}
MAX_FAILURES, FAILURE_WINDOW_S = 5, 15 * 60


class AuthError(ValueError):
    pass


def normalize_login(raw: str) -> str:
    """Email (lower-cased) or mobile number in E.164 form (numbers without a country code are Indian)."""
    try:
        return contact.normalize_login(raw)
    except contact.ContactError as e:
        raise AuthError(str(e)) from e


def check_password_strength(password: str) -> None:
    if len(password) < 8:
        raise AuthError("Password must be at least 8 characters")
    if len(password) > 200:
        raise AuthError("Password is too long")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    return "scrypt${n}${r}${p}${salt}${dk}".format(**_SCRYPT, salt=base64.b64encode(salt).decode(), dk=base64.b64encode(dk).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, dk = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), dklen=32, n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(got, base64.b64decode(dk))
    except (ValueError, TypeError):
        return False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# Throttle password guessing per login (in-process; enough for a single-server deployment).
_failures: dict[str, list[float]] = {}
_lock = threading.Lock()


def _check_throttle(login: str) -> None:
    now = time.monotonic()
    with _lock:
        recent = [t for t in _failures.get(login, []) if now - t < FAILURE_WINDOW_S]
        _failures[login] = recent
        if len(recent) >= MAX_FAILURES:
            raise AuthError("Too many failed attempts. Please wait 15 minutes and try again")


def _record_failure(login: str) -> None:
    with _lock:
        _failures.setdefault(login, []).append(time.monotonic())


def register(db: Session, name: str, login: str, password: str) -> Account:
    login = normalize_login(login)
    if not name.strip():
        raise AuthError("Please enter your name")
    check_password_strength(password)
    if db.exec(select(Account).where(Account.login == login)).first():
        raise AuthError("An account with this email or mobile number already exists. Please sign in")
    acc = Account(login=login, name=name.strip(), password_hash=hash_password(password))
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


def authenticate(db: Session, login: str, password: str) -> Account:
    login = normalize_login(login)
    _check_throttle(login)
    acc = db.exec(select(Account).where(Account.login == login)).first()
    if not acc or not verify_password(password, acc.password_hash):
        _record_failure(login)
        raise AuthError("Incorrect email/mobile number or password")
    with _lock:
        _failures.pop(login, None)
    return acc


def create_session(db: Session, account: Account) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db.add(AuthSession(token_hash=_hash_token(token), account_id=account.id, created_at=now,
                       expires_at=now + timedelta(days=get_settings().session_days)))
    db.commit()
    return token


def account_for_token(db: Session, token: str | None) -> Account | None:
    if not token:
        return None
    sess = db.get(AuthSession, _hash_token(token))
    if not sess:
        return None
    if _utc(sess.expires_at) < datetime.now(timezone.utc):
        db.delete(sess)
        db.commit()
        return None
    return db.get(Account, sess.account_id)


def end_session(db: Session, token: str | None) -> None:
    if token and (sess := db.get(AuthSession, _hash_token(token))):
        db.delete(sess)
        db.commit()


def end_all_sessions(db: Session, account_id: str, keep_token: str | None = None) -> None:
    keep = _hash_token(keep_token) if keep_token else None
    for s in db.exec(select(AuthSession).where(AuthSession.account_id == account_id)).all():
        if s.token_hash != keep:
            db.delete(s)
    db.commit()


def update_account(db: Session, acc: Account, name: str | None, login: str | None, current_password: str | None) -> Account:
    if name is not None:
        if not name.strip():
            raise AuthError("Please enter your name")
        acc.name = name.strip()[:100]
    if login is not None:
        new_login = normalize_login(login)
        if new_login != acc.login:
            if not current_password or not verify_password(current_password, acc.password_hash):
                raise AuthError("Enter your current password to change your email or mobile number")
            if db.exec(select(Account).where(Account.login == new_login)).first():
                raise AuthError("Another account already uses this email or mobile number")
            acc.login = new_login
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


def change_password(db: Session, acc: Account, current_password: str, new_password: str, keep_token: str | None) -> None:
    if not verify_password(current_password, acc.password_hash):
        raise AuthError("Your current password is incorrect")
    check_password_strength(new_password)
    acc.password_hash = hash_password(new_password)
    db.add(acc)
    db.commit()
    end_all_sessions(db, acc.id, keep_token=keep_token)
