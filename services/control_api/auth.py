from __future__ import annotations

import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer_scheme = HTTPBearer(auto_error=False)


def expected_token() -> str | None:
    token = os.getenv("CONTROL_API_TOKEN")
    if token is None or not token.strip():
        return None
    return token


def require_auth(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> None:
    token = expected_token()
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CONTROL_API_TOKEN is not configured",
        )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    if not secrets.compare_digest(credentials.credentials, token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")
