"""HTTP Bearer JWT dependency (works with auth middleware setting request.state)."""

from typing import Optional

from fastapi import Header, HTTPException, Request

from utils.jwt_utils import decode_access_token


def _bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization.split(" ", 1)[1].strip() or None


def user_id_dep(request: Request) -> str:
    """Resolve current user id from middleware (preferred) or Authorization header."""
    uid = getattr(request.state, "user_id", None)
    if uid:
        return uid
    auth = request.headers.get("Authorization")
    token = _bearer_token(auth)
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        payload = decode_access_token(token)
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return str(sub)
    except Exception:
        raise HTTPException(status_code=401, detail="Unauthorized") from None


def optional_user_id_dep(
    request: Request,
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> Optional[str]:
    if getattr(request.state, "user_id", None):
        return str(request.state.user_id)
    token = _bearer_token(authorization)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        sub = payload.get("sub")
        return str(sub) if sub else None
    except Exception:
        return None
