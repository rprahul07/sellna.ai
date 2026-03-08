"""JWT-based authentication & authorization.

Supports two roles:
  - "admin"   — full access
  - "service" — inter-service calls

Usage in endpoints:
    @router.get("/protected")
    async def protected(user: TokenData = Depends(require_role("admin"))):
        ...
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import get_settings

_settings = get_settings()
_bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Token model
# ---------------------------------------------------------------------------


class TokenData(BaseModel):
    sub: str  # user_id or service name
    role: str  # "admin" | "service"
    exp: datetime


# ---------------------------------------------------------------------------
# Token creation (used by login/bootstrap endpoints)
# ---------------------------------------------------------------------------


def create_access_token(sub: str, role: str = "admin") -> str:
    """Return a signed JWT access token."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=_settings.jwt_expire_minutes)
    payload = {
        "sub": sub,
        "role": role,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, _settings.secret_key, algorithm=_settings.jwt_algorithm)


# ---------------------------------------------------------------------------
# Token verification
# ---------------------------------------------------------------------------


async def _get_current_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> TokenData:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(
            credentials.credentials,
            _settings.secret_key,
            algorithms=[_settings.jwt_algorithm],
        )
        return TokenData(
            sub=payload["sub"],
            role=payload.get("role", "admin"),
            exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_role(*roles: str):
    """FastAPI dependency factory for role-based access control."""

    async def _check(token: Annotated[TokenData, Depends(_get_current_token)]) -> TokenData:
        if token.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{token.role}' is not allowed. Required: {roles}",
            )
        return token

    return _check


# Convenience shorthand
get_current_user = _get_current_token
