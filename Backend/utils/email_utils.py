"""FastAPI-Mail SMTP helpers for OTP delivery."""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType

_env = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env)


def _normalize_mail_password() -> str:
    raw = (os.getenv("MAIL_PASSWORD") or "").strip()
    if "#" in raw:
        raw = raw.split("#")[0].strip()
    return raw.replace(" ", "")


def get_mail_connection_config() -> ConnectionConfig:
    port = int(os.getenv("MAIL_PORT", "587"))
    starttls = os.getenv("MAIL_STARTTLS", "True").lower() in ("true", "1", "yes")
    ssl_tls = os.getenv("MAIL_SSL_TLS", "False").lower() in ("true", "1", "yes")
    use_creds = os.getenv("MAIL_USE_CREDENTIALS", "True").lower() in ("true", "1", "yes")
    validate = os.getenv("MAIL_VALIDATE_CERTS", "True").lower() in ("true", "1", "yes")
    return ConnectionConfig(
        MAIL_USERNAME=os.getenv("MAIL_USERNAME", ""),
        MAIL_PASSWORD=_normalize_mail_password(),
        MAIL_FROM=os.getenv("MAIL_FROM", ""),
        MAIL_PORT=port,
        MAIL_SERVER=os.getenv("MAIL_SERVER", "smtp.gmail.com"),
        MAIL_FROM_NAME=os.getenv("MAIL_FROM_NAME", "HireMantra"),
        MAIL_STARTTLS=starttls,
        MAIL_SSL_TLS=ssl_tls,
        USE_CREDENTIALS=use_creds,
        VALIDATE_CERTS=validate,
    )


async def send_otp_email(to_email: str, otp: str) -> None:
    conf = get_mail_connection_config()
    fm = FastMail(conf)
    body = (
        f"<p>Your HireMantra verification code is: <strong>{otp}</strong></p>"
        "<p>This code expires in 5 minutes.</p>"
    )
    message = MessageSchema(
        subject="Your HireMantra verification code",
        recipients=[to_email],
        body=body,
        subtype=MessageType.html,
    )
    await fm.send_message(message)
