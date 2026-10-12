"""Emails beyond codes: security alerts (sent right away) and a daily job for medicine reminders and weekly summaries.

The daily job is started by a scheduled GitHub Action (.github/workflows/notify.yml), because a sleeping free Render
service runs no timers. It is idempotent: running it twice on a day sends nothing new.
"""

import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlmodel import Session, col, select

from app.config import get_settings
from app.fhir.mapper import IST
from app.models.tables import Account, Document, MedicationRequest, Notification, Observation, Patient
from app.services import mailer
from app.services.records import medication_status

log = logging.getLogger(__name__)
WEEK = timedelta(days=7)
REMIND_BEFORE_DAYS, REMIND_AFTER_DAYS = 2, 3
FLAG_WORDS = {"H": "high", "L": "low", "HH": "very high", "LL": "very low", "A": "abnormal"}
NOT_ADVICE = "Health Copilot explains your records; it doesn't replace your doctor."


def _url(path: str = "") -> str:
    return get_settings().app_url.rstrip("/") + path


def _when(dt: datetime) -> str:
    return dt.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST").lstrip("0")


def device_name(user_agent: str | None) -> str:
    ua = user_agent or ""
    browser = next((name for pat, name in (("Edg/", "Edge"), ("OPR/", "Opera"), ("SamsungBrowser", "Samsung Internet"),
                                           ("Firefox/", "Firefox"), ("Chrome/", "Chrome"), ("Safari/", "Safari"))
                    if pat in ua), "a browser")
    system = next((name for pat, name in ((r"iPhone|iPad", "iOS"), (r"Android", "Android"), (r"Windows", "Windows"),
                                          (r"Mac OS X|Macintosh", "macOS"), (r"CrOS", "ChromeOS"), (r"Linux", "Linux"))
                   if re.search(pat, ua)), None)
    return f"{browser} on {system}" if system else browser


def security_alert(email: str, name: str, event: str, *, device: str | None = None, new_email: str | None = None) -> None:
    """Tell the account holder about a sign-in or a change to their account. Never raises."""
    now = _when(datetime.now(timezone.utc))
    reset_hint = "If this wasn't you, reset your password right away and check your account."
    texts = {
        "sign_in": ("New sign-in to Health Copilot",
                    [f"Hi {name}, your account was signed in to on {now} from {device or 'a browser'}.",
                     "If this was you, there's nothing to do. " + reset_hint]),
        "password_changed": ("Your Health Copilot password was changed",
                             [f"Hi {name}, the password for your account was changed on {now}. Other devices were signed out.",
                              reset_hint]),
        "password_reset": ("Your Health Copilot password was reset",
                           [f"Hi {name}, the password for your account was reset with an email code on {now}. "
                            "Every device was signed out.", reset_hint]),
        "email_changed": ("The email on your Health Copilot account was changed",
                          [f"Hi {name}, the email for codes and alerts on your account was changed to {new_email} on {now}. "
                           "This address will no longer get them.", reset_hint]),
    }
    subject, paragraphs = texts[event]
    try:
        mailer.send(email, subject, paragraphs, button=("Reset password", _url("/?forgot=1")),
                    footer="You get security alerts for your account. You can turn them off in Your account.")
    except mailer.MailError as e:
        log.warning("Security alert %s not sent: %s", event, e)


def _value(o: Observation) -> str:
    if o.value_text:
        return o.value_text
    if o.value_num is None:
        return ""
    return f"{o.value_num:g}" + (f" {o.unit}" if o.unit else "")


def _medicine_lines(db: Session, acc: Account, patients: list[Patient], today: date) -> tuple[list[str], list[str]]:
    lines, keys = [], []
    for p in patients:
        meds = db.exec(select(MedicationRequest).where(MedicationRequest.patient_id == p.id, MedicationRequest.status == "active")).all()
        for m in meds:
            if not (m.duration_days and m.authored_on):
                continue
            last_day = m.authored_on + timedelta(days=m.duration_days - 1)
            left = (last_day - today).days
            key = f"med:{m.id}"
            if not -REMIND_AFTER_DAYS <= left <= REMIND_BEFORE_DAYS:
                continue
            if db.exec(select(Notification).where(Notification.account_id == acc.id, Notification.key == key)).first():
                continue
            when = (f"ended on {last_day:%d %b}" if left < 0 else "ends today" if left == 0 else "ends tomorrow" if left == 1
                    else f"ends in {left} days, on {last_day:%d %b}")
            drug = " ".join(x for x in (m.name, m.strength) if x)
            lines.append(f"{p.name}: {drug}, a {m.duration_days}-day course, {when}.")
            keys.append(key)
    return lines, keys


def _weekly_lines(db: Session, patients: list[Patient], now: datetime, today: date) -> list[str]:
    lines = []
    for p in patients:
        docs = db.exec(select(Document).where(Document.patient_id == p.id, Document.status == "confirmed",
                                              col(Document.confirmed_at) >= now - WEEK)).all()
        meds = db.exec(select(MedicationRequest).where(MedicationRequest.patient_id == p.id)).all()
        active = [m for m in meds if medication_status(m, today) == "active"]
        if not docs and not active:
            continue
        parts = [f"{len(docs)} new record{'s' if len(docs) != 1 else ''}" if docs else "no new records"]
        if docs:
            flagged = db.exec(select(Observation).where(col(Observation.document_id).in_([d.id for d in docs]),
                                                        col(Observation.interpretation).in_(list(FLAG_WORDS)))).all()
            if flagged:
                shown = ", ".join(f"{o.name} {_value(o)} ({FLAG_WORDS[o.interpretation or 'A']})".replace("  ", " ")
                                  for o in flagged[:4])
                more = f" and {len(flagged) - 4} more" if len(flagged) > 4 else ""
                parts.append(f"outside the usual range: {shown}{more}")
        if active:
            parts.append(f"{len(active)} active medicine{'s' if len(active) != 1 else ''}")
        lines.append(f"{p.name}: " + "; ".join(parts) + ".")
    return lines


def run_daily(db: Session, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(IST).date()
    sent = {"medicines": 0, "weekly": 0, "failed": 0}
    accounts = db.exec(select(Account).where(col(Account.email_verified_at).is_not(None), col(Account.email).is_not(None))).all()
    for acc in accounts:
        patients = list(db.exec(select(Patient).where(Patient.owner_id == acc.id).order_by(col(Patient.created_at))).all())
        if acc.notify_medicines:
            lines, keys = _medicine_lines(db, acc, patients, today)
            if lines:
                try:
                    mailer.send(acc.email or "", "Medicine course reminder from Health Copilot",
                                [f"Hi {acc.name}, these medicine courses are ending or have just ended:", *lines,
                                 "Please check with your doctor before stopping, continuing or repeating a medicine.",
                                 NOT_ADVICE],
                                button=("Open medicines", _url("/medications")),
                                footer="You get medicine reminders. You can turn them off in Your account.")
                    db.add_all(Notification(account_id=acc.id, key=k) for k in keys)
                    sent["medicines"] += 1
                except mailer.MailError:
                    sent["failed"] += 1
        since = acc.last_weekly_at or acc.created_at
        since = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
        if acc.notify_weekly and now - since >= WEEK - timedelta(hours=2):
            lines = _weekly_lines(db, patients, now, today)
            if lines:
                try:
                    mailer.send(acc.email or "", "Your weekly Health Copilot summary",
                                [f"Hi {acc.name}, here is your family's week in Health Copilot:", *lines,
                                 "Open the app for details, trends and plain-language explanations.", NOT_ADVICE],
                                button=("Open Health Copilot", _url("/")),
                                footer="You get a weekly summary. You can turn it off in Your account.")
                    sent["weekly"] += 1
                except mailer.MailError:
                    sent["failed"] += 1
                    continue
            acc.last_weekly_at = now
            db.add(acc)
        db.commit()
    return sent
