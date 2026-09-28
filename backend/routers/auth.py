from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import Role, User
from security import create_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-zA-Z0-9_.]+$")
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=160)
    password: str = Field(min_length=8, max_length=128)
    program: Optional[str] = Field(default=None, max_length=10)
    batch_year: Optional[int] = Field(default=None, ge=2000, le=2100)


class LoginIn(BaseModel):
    username: str
    password: str


def user_out(u: User):
    sp = u.staff_profile
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "email": u.email, "role": u.role_name,
            "batch": u.batch_label, "department_id": sp.department_id if sp else None,
            "department": sp.department.name if sp and sp.department else None,
            "hierarchy_level": sp.hierarchy_level if sp else None, "title": sp.title if sp else None}


@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    """Self-registration always creates a STUDENT. Staff accounts are created by admins."""
    if db.query(User).filter((User.username == body.username) | (User.email == body.email)).first():
        raise HTTPException(400, "Username or email already registered")
    role = db.query(Role).filter_by(name="STUDENT").first()
    u = User(username=body.username, full_name=body.full_name, email=body.email, password_hash=hash_password(body.password),
             role_id=role.id, program=(body.program or "").upper() or None, batch_year=body.batch_year)
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"access_token": create_token(u), "token_type": "bearer", "user": user_out(u)}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(username=body.username.strip()).first()
    if not u or not verify_password(body.password, u.password_hash) or not u.is_active:
        raise HTTPException(401, "Invalid username or password")
    return {"access_token": create_token(u), "token_type": "bearer", "user": user_out(u)}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_out(user)
