from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import current_account
from app.config import get_settings
from app.db import get_session
from app.models.tables import Account, Patient
from app.services import auth
from app.services.records import delete_patient

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    name: str
    login: str
    password: str


class LoginIn(BaseModel):
    login: str
    password: str


class DeleteIn(BaseModel):
    password: str


def _account_out(a: Account) -> dict[str, Any]:
    return {"id": a.id, "name": a.name, "login": a.login, "created_at": a.created_at}


def _start_session(resp: Response, db: Session, acc: Account) -> None:
    s = get_settings()
    resp.set_cookie(auth.COOKIE, auth.create_session(db, acc), max_age=s.session_days * 86400,
                    httponly=True, samesite="lax", secure=s.cookie_secure, path="/")


@router.post("/register")
def register(body: RegisterIn, resp: Response, db: Session = Depends(get_session)):
    try:
        acc = auth.register(db, body.name, body.login, body.password)
    except auth.AuthError as e:
        raise HTTPException(400, str(e)) from e
    _start_session(resp, db, acc)
    return _account_out(acc)


@router.post("/login")
def login(body: LoginIn, resp: Response, db: Session = Depends(get_session)):
    try:
        acc = auth.authenticate(db, body.login, body.password)
    except auth.AuthError as e:
        raise HTTPException(401, str(e)) from e
    _start_session(resp, db, acc)
    return _account_out(acc)


@router.post("/logout")
def logout(request: Request, resp: Response, db: Session = Depends(get_session)):
    auth.end_session(db, request.cookies.get(auth.COOKIE))
    resp.delete_cookie(auth.COOKIE, path="/")
    return {"signed_out": True}


@router.get("/me")
def me(acc: Account = Depends(current_account)):
    return _account_out(acc)


@router.post("/delete-account")
def delete_account(body: DeleteIn, resp: Response, acc: Account = Depends(current_account), db: Session = Depends(get_session)):
    """Delete the account and every profile, document and uploaded file it owns."""
    if not auth.verify_password(body.password, acc.password_hash):
        raise HTTPException(401, "Incorrect password")
    for p in db.exec(select(Patient).where(Patient.owner_id == acc.id)).all():
        delete_patient(db, p)
    auth.end_all_sessions(db, acc.id)
    db.delete(acc)
    db.commit()
    resp.delete_cookie(auth.COOKIE, path="/")
    return {"deleted": True}
