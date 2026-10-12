from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from app.db import get_session
from app.models.tables import Account, Document, Patient
from app.services import auth


def current_account(request: Request, db: Session = Depends(get_session)) -> Account:
    acc = auth.account_for_token(db, request.cookies.get(auth.COOKIE))
    if not acc:
        raise HTTPException(401, "Please sign in")
    return acc


def patient_or_404(patient_id: str, acc: Account = Depends(current_account), db: Session = Depends(get_session)) -> Patient:
    p = db.get(Patient, patient_id)
    # Someone else's profile looks exactly like a missing one, so IDs cannot be probed.
    if not p or p.owner_id != acc.id:
        raise HTTPException(404, "Patient not found")
    return p


def document_or_404(document_id: str, acc: Account = Depends(current_account), db: Session = Depends(get_session)) -> Document:
    d = db.get(Document, document_id)
    p = db.get(Patient, d.patient_id) if d else None
    if not d or not p or p.owner_id != acc.id:
        raise HTTPException(404, "Document not found")
    return d


def llm_error(e: Exception) -> HTTPException:
    return HTTPException(503, f"AI service temporarily unavailable: {str(e)[:300]}")
