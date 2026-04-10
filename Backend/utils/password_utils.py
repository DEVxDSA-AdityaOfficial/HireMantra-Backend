"""Password hashing with bcrypt (native library; avoids passlib + bcrypt API drift)."""

import bcrypt


def _password_bytes(plain: str) -> bytes:
    """Bcrypt only considers the first 72 bytes of the password."""
    b = plain.encode("utf-8")
    if len(b) > 72:
        return b[:72]
    return b


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_password_bytes(plain), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(_password_bytes(plain), hashed.encode("ascii"))
    except ValueError:
        return False
