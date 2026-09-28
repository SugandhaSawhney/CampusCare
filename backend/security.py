"""Password hashing (PBKDF2-SHA256, stdlib), JWT auth, role dependencies."""
import base64
import hashlib
import hmac
import os
from datetime import timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, SECRET_KEY
from database import get_db, utcnow
from models import User

PBKDF2_ITERATIONS = 240_000
bearer = HTTPBearer(auto_error=False)

STUDENT, TRIAGE, STAFF, DEAN, ADMIN = "STUDENT", "TRIAGE_AGENT", "DEPARTMENT_STAFF", "DEAN", "ADMIN"
STAFF_ROLES = {TRIAGE, STAFF, DEAN, ADMIN}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt_b64, dk_b64 = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except Exception:
        return False


def create_token(user: User) -> str:
    payload = {"sub": str(user.id), "role": user.role_name, "exp": utcnow() + timedelta(minutes=JWT_EXPIRE_MINUTES)}
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def get_current_user(creds: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive")
    return user  # role is always re-read from the DB, never trusted from the token


def require_roles(*roles):
    def dep(user: User = Depends(get_current_user)) -> User:
        if user.role_name not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role: {', '.join(roles)}")
        return user
    return dep
