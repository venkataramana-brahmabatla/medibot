"""
src/api/auth.py
---------------
Authentication and JWT token handling for MediBot FastAPI backend.

Demo Accounts (User -> Password -> Role):
  - dr.mehta / doctor123           -> doctor
  - nurse.priya / nurse123         -> nurse
  - billing.ravi / billing123       -> billing_executive
  - tech.anand / tech123           -> technician
  - admin.sys / admin123           -> admin
"""

from datetime import datetime, timedelta
from typing import Optional
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from src.config import settings

# -----------------------------------------------------------------------------
# Demo Accounts Database
# -----------------------------------------------------------------------------
DEMO_USERS = {
    "dr.mehta": {
        "username": "dr.mehta",
        "password": "doctor123",
        "full_name": "Dr. Rajesh Mehta",
        "role": "doctor",
        "department": "Clinical Cardiology",
    },
    "nurse.priya": {
        "username": "nurse.priya",
        "password": "nurse123",
        "full_name": "Nurse Priya Sharma",
        "role": "nurse",
        "department": "ICU Nursing",
    },
    "billing.ravi": {
        "username": "billing.ravi",
        "password": "billing123",
        "full_name": "Ravi Kumar",
        "role": "billing_executive",
        "department": "Billing & Insurance",
    },
    "tech.anand": {
        "username": "tech.anand",
        "password": "tech123",
        "full_name": "Anand Verma",
        "role": "technician",
        "department": "Medical Equipment Maintenance",
    },
    "admin.sys": {
        "username": "admin.sys",
        "password": "admin123",
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
    username: str
    password: str


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
    expire = datetime.utcnow() + timedelta(hours=settings.jwt_expiry_hours)
    payload = {
        "sub": user_data["username"],
        "role": user_data["role"],
        "full_name": user_data["full_name"],
        "exp": expire,
    }
    encoded_jwt = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt


def verify_token(token: str) -> Optional[UserPayload]:
    """
    Verifies JWT token signature and expiry.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
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
