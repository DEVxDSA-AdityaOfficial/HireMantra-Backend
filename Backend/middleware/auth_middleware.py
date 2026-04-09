"""JWT validation for protected API routes; public routes bypass."""

from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from utils.jwt_utils import decode_access_token


def _normalize_path(path: str) -> str:
    p = path.rstrip("/")
    return p if p else "/"


def _is_public_path(path: str) -> bool:
    p = _normalize_path(path)
    public = {
        "/",
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/auth/request-otp",
        "/api/auth/verify-otp",
    }
    return p in public


def _extract_bearer(request: Request) -> str | None:
    auth = request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    return token or None


class JWTAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        path = _normalize_path(request.url.path)
        if not path.startswith("/api"):
            return await call_next(request)

        if _is_public_path(request.url.path):
            return await call_next(request)

        token = _extract_bearer(request)
        if not token:
            return JSONResponse(
                status_code=401,
                content={"status": False, "message": "Missing or invalid Authorization", "data": None},
            )
        try:
            payload = decode_access_token(token)
            sub = payload.get("sub")
            if not sub:
                raise ValueError("missing sub")
            request.state.user_id = str(sub)
        except Exception:
            return JSONResponse(
                status_code=401,
                content={"status": False, "message": "Invalid or expired token", "data": None},
            )

        return await call_next(request)
