from fastapi import Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.models.tables import Document, Patient


def patient_or_404(patient_id: str, db: Session = Depends(get_session)) -> Patient:
    p = db.get(Patient, patient_id)
    if not p:
        raise HTTPException(404, "Patient not found")
    return p


def document_or_404(document_id: str, db: Session = Depends(get_session)) -> Document:
    d = db.get(Document, document_id)
    if not d:
        raise HTTPException(404, "Document not found")
    return d


def llm_error(e: Exception) -> HTTPException:
    return HTTPException(503, f"AI service temporarily unavailable: {str(e)[:300]}")
