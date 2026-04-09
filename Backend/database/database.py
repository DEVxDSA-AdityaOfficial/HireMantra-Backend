import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


def _strip_env(value: str | None) -> str | None:
    if value is None:
        return None
    s = value.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        return s[1:-1]
    return s


def _build_mysql_url() -> str | None:
    host = _strip_env(os.getenv("DATABASE_HOST_2"))
    port_s = _strip_env(os.getenv("DATABASE_PORT_2")) or "3306"
    user = _strip_env(os.getenv("DATABASE_USER_2"))
    password = _strip_env(os.getenv("DATABASE_PASSWORD_2"))
    name = _strip_env(os.getenv("DATABASE_NAME_2"))
    if not all([host, user, password is not None, name]):
        return None
    try:
        port = int(port_s)
    except ValueError:
        port = 3306
    user_q = quote_plus(user)
    pwd_q = quote_plus(password or "")
    return f"mysql+pymysql://{user_q}:{pwd_q}@{host}:{port}/{name}"


_mysql_url = _build_mysql_url()
if _mysql_url:
    DATABASE_URL = _mysql_url
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
else:
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    connect_args = (
        {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
    )
    engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
