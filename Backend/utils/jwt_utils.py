"""JWT create and decode helpers."""

import os
from datetime import datetime, timedelta
from typing import Any, Optional

import jwt
from dotenv import load_dotenv
from pathlib import Path

_env = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env)

JWT_SECRET = os.getenv("JWT_SECRET", "change_me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_DAYS = int(os.getenv("JWT_EXPIRATION_DAYS", "180"))


def create_access_token(payload: dict[str, Any], days: Optional[int] = None) -> str:
    to_encode = payload.copy()
    exp_days = days if days is not None else JWT_EXPIRATION_DAYS
    to_encode["exp"] = datetime.utcnow() + timedelta(days=exp_days)
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
