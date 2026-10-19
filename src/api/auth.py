"""
src/api/auth.py
---------------
Authentication and JWT token handling for MediBot FastAPI backend.

Local demo identities are available only when demo authentication is enabled
in a development environment. The shared password is loaded from .env.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from src.config import ALL_ROLES, settings

# -----------------------------------------------------------------------------
# Local development identities only. Passwords are supplied out of band through
# DEMO_AUTH_PASSWORD and demo mode is rejected outside APP_ENV=development.
# -----------------------------------------------------------------------------
DEMO_USERS = {
    "dr.mehta": {
        "username": "dr.mehta",
        "full_name": "Dr. Rajesh Mehta",
        "role": "doctor",
        "department": "Clinical Cardiology",
    },
    "nurse.priya": {
        "username": "nurse.priya",
        "full_name": "Nurse Priya Sharma",
        "role": "nurse",
        "department": "ICU Nursing",
    },
    "billing.ravi": {
        "username": "billing.ravi",
        "full_name": "Ravi Kumar",
        "role": "billing_executive",
        "department": "Billing & Insurance",
    },
    "tech.anand": {
        "username": "tech.anand",
        "full_name": "Anand Verma",
        "role": "technician",
        "department": "Medical Equipment Maintenance",
    },
    "admin.sys": {
        "username": "admin.sys",
        "full_name": "System Administrator",
        "role": "admin",
        "department": "IT & Executive Admin",
    },
}

security = HTTPBearer(auto_error=False)


# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str
    full_name: str


class UserPayload(BaseModel):
    username: str
    role: str
    full_name: str


# -----------------------------------------------------------------------------
# JWT Utilities
# -----------------------------------------------------------------------------
def create_access_token(user_data: dict) -> str:
    """
    Generates a role-tagged JWT access token.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=settings.jwt_expiry_hours)
    payload = {
        "sub": user_data["username"],
        "role": user_data["role"],
        "full_name": user_data["full_name"],
        "iat": now,
        "exp": expire,
        "iss": "medibot",
        "aud": "medibot-client",
        "typ": "access",
    }
    encoded_jwt = jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")
    return encoded_jwt


def verify_token(token: str) -> Optional[UserPayload]:
    """
    Verifies JWT token signature and expiry.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=["HS256"],
            issuer="medibot",
            audience="medibot-client",
            options={"require": ["sub", "role", "exp", "iat", "iss", "aud", "typ"]},
        )
        if payload.get("typ") != "access" or payload.get("role") not in ALL_ROLES:
            return None
        return UserPayload(
            username=payload["sub"],
            role=payload["role"],
            full_name=payload.get("full_name", payload["sub"]),
        )
    except (jwt.PyJWTError, KeyError):
        return None


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> UserPayload:
    """
    FastAPI dependency for authenticating requests via Bearer token.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing. Bearer token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = verify_token(credentials.credentials)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
