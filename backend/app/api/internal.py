import hmac

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.services import notifications

router = APIRouter(prefix="/api/internal", include_in_schema=False)


@router.post("/notifications/run")
def run_notifications(x_cron_secret: str = Header(""), db: Session = Depends(get_session)):
    """Daily reminders and weekly summaries, started by the scheduled GitHub Action."""
    secret = get_settings().cron_secret
    if not secret or not hmac.compare_digest(x_cron_secret.encode(), secret.encode()):
        raise HTTPException(404, "Not found")
    return notifications.run_daily(db)
