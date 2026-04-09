"""
One-time (or idempotent): CREATE DATABASE IF NOT EXISTS from .env DATABASE_*_2 vars.

Run from Backend/: python -m scripts.create_mysql_database
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")


def _strip(value: str | None) -> str | None:
    if value is None:
        return None
    s = value.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        return s[1:-1]
    return s


def main() -> int:
    host = _strip(os.getenv("DATABASE_HOST_2"))
    port_s = _strip(os.getenv("DATABASE_PORT_2")) or "3306"
    user = _strip(os.getenv("DATABASE_USER_2"))
    password = _strip(os.getenv("DATABASE_PASSWORD_2"))
    name = _strip(os.getenv("DATABASE_NAME_2"))
    if not all([host, user, password is not None, name]):
        print("Missing DATABASE_HOST_2 / DATABASE_USER_2 / DATABASE_PASSWORD_2 / DATABASE_NAME_2", file=sys.stderr)
        return 1
    try:
        port = int(port_s)
    except ValueError:
        port = 3306

    import pymysql

    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password or "",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
        print(f"Database `{name}` is ready on {host}:{port}.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
