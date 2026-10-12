"""Sending email through a Google Apps Script web app that runs on your own Google account and sends from your Gmail
(free: about 100 emails a day). The script is in scripts/google-apps-script/Code.gs.

Render's free plan blocks outgoing SMTP, so Gmail's SMTP server cannot be used there; the script is reached over HTTPS.
Without GOOGLE_SCRIPT_URL on a local http:// server, emails are only logged and kept in `outbox`, and codes are shown
on screen instead.
"""

import html
import logging
from dataclasses import dataclass

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)
NOT_SENT = "We couldn't send the email just now. Please try again in a minute"


class MailError(RuntimeError):
    pass


@dataclass
class Mail:
    to: str
    subject: str
    text: str
    html: str


outbox: list[Mail] = []  # local development and tests only


def send(to: str, subject: str, paragraphs: list[str], *, code: str | None = None, button: tuple[str, str] | None = None,
         footer: str | None = None) -> None:
    mail = _render(to, subject, paragraphs, code, button, footer)
    s = get_settings()
    if not s.google_script_url:
        if not s.mail_debug:
            raise MailError("Email isn't set up on this server yet. Please try again later")
        outbox.append(mail)
        del outbox[:-50]
        log.info("Email to %s (not sent, no GOOGLE_SCRIPT_URL): %s", to, subject)
        return
    body = {"secret": s.google_script_secret, "to": to, "subject": subject, "text": mail.text, "html": mail.html,
            "name": s.mail_from_name}
    try:
        # The web app answers a POST with a redirect to its output, which httpx fetches with a GET.
        with httpx.Client(verify=s.ca_bundle or True, timeout=40, follow_redirects=True) as c:
            r = c.post(s.google_script_url, json=body)
        reply = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.error("Google Apps Script request failed: %s", type(e).__name__)
        raise MailError(NOT_SENT) from e
    if not (isinstance(reply, dict) and reply.get("ok")):
        log.error("Google Apps Script did not send the email: %s", str(reply)[:300])
        raise MailError(NOT_SENT)


def _render(to: str, subject: str, paragraphs: list[str], code: str | None, button: tuple[str, str] | None,
            footer: str | None) -> Mail:
    s = get_settings()
    text = "\n\n".join([*paragraphs, *([code] if code else []), *([f"{button[0]}: {button[1]}"] if button else []),
                        *([footer] if footer else []), "Health Copilot"])
    esc = html.escape
    parts = [f'<p style="margin:0 0 14px;line-height:1.55">{esc(p)}</p>' for p in paragraphs]
    if code:
        parts.append('<p style="margin:22px 0;font-size:30px;font-weight:700;letter-spacing:8px;color:#0f766e;'
                     f'font-family:ui-monospace,Menlo,Consolas,monospace">{esc(code)}</p>')
    if button:
        parts.append(f'<p style="margin:22px 0"><a href="{esc(button[1])}" style="background:#0d9488;color:#fff;'
                     'padding:11px 20px;border-radius:10px;text-decoration:none;font-weight:600;display:inline-block">'
                     f'{esc(button[0])}</a></p>')
    foot = esc(footer) + "<br>" if footer else ""
    page = (
        '<div style="background:#f1f5f9;padding:28px 12px;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'color:#0f172a;font-size:15px">'
        '<div style="max-width:520px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden;'
        'border:1px solid #e2e8f0">'
        '<div style="background:#0f766e;color:#fff;padding:16px 24px;font-weight:700;font-size:17px">Health Copilot</div>'
        f'<div style="padding:24px">{"".join(parts)}</div></div>'
        f'<p style="max-width:520px;margin:14px auto 0;color:#64748b;font-size:12px;line-height:1.5">{foot}'
        f'<a href="{esc(s.app_url)}" style="color:#0f766e">{esc(s.app_url.removeprefix("https://"))}</a></p></div>'
    )
    return Mail(to=to, subject=subject, text=text, html=page)
