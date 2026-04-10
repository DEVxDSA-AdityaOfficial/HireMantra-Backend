"""FastAPI-Mail SMTP helpers for OTP delivery."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType

_env = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env)

logger = logging.getLogger(__name__)


def _conf_plain(val) -> str:
    """ConnectionConfig may wrap secrets as Pydantic ``SecretStr`` — never call ``.strip()`` on it raw."""
    if val is None:
        return ""
    if hasattr(val, "get_secret_value"):
        try:
            inner = val.get_secret_value()
        except Exception:
            inner = val
        return str(inner or "").strip()
    return str(val).strip()


def _normalize_mail_password() -> str:
    raw = (os.getenv("MAIL_PASSWORD") or "").strip()
    if "#" in raw:
        raw = raw.split("#")[0].strip()
    return raw.replace(" ", "")


def _mail_config_issues(conf: ConnectionConfig) -> list[str]:
    """Human-readable problems if SMTP is not usable."""
    issues: list[str] = []
    u = _conf_plain(getattr(conf, "MAIL_USERNAME", None))
    p = _conf_plain(getattr(conf, "MAIL_PASSWORD", None))
    f = _conf_plain(getattr(conf, "MAIL_FROM", None))
    srv = _conf_plain(getattr(conf, "MAIL_SERVER", None))
    if not u:
        issues.append("MAIL_USERNAME is empty")
    if not p:
        issues.append("MAIL_PASSWORD is empty (use a Gmail App Password if using Gmail)")
    if not f:
        issues.append("MAIL_FROM is empty")
    if not srv:
        issues.append("MAIL_SERVER is empty")
    return issues


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
    if (os.getenv("MAIL_SUPPRESS_SEND") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        logger.warning(
            "MAIL_SUPPRESS_SEND is set; OTP email to %s not sent (dev only)",
            to_email,
        )
        return

    conf = get_mail_connection_config()
    bad = _mail_config_issues(conf)
    if bad:
        raise ValueError("Email not configured: " + "; ".join(bad))

    u = _conf_plain(getattr(conf, "MAIL_USERNAME", None)).lower()
    f = _conf_plain(getattr(conf, "MAIL_FROM", None)).lower()
    srv = _conf_plain(getattr(conf, "MAIL_SERVER", None)).lower()
    if u and f and u != f and "gmail" in srv:
        logger.warning(
            "MAIL_FROM (%s) differs from MAIL_USERNAME (%s); Gmail may reject or drop mail",
            _conf_plain(getattr(conf, "MAIL_FROM", None)),
            _conf_plain(getattr(conf, "MAIL_USERNAME", None)),
        )

    logger.info(
        "SMTP: sending OTP via %s:%s (from=%s, to=%s)",
        _conf_plain(getattr(conf, "MAIL_SERVER", None)),
        getattr(conf, "MAIL_PORT", ""),
        _conf_plain(getattr(conf, "MAIL_FROM", None)),
        to_email,
    )

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
    try:
        await fm.send_message(message)
    except Exception as e:
        logger.exception(
            "SMTP failed sending OTP to %s (server=%s port=%s): %s",
            to_email,
            _conf_plain(getattr(conf, "MAIL_SERVER", None)),
            getattr(conf, "MAIL_PORT", ""),
            e,
        )
        raise RuntimeError(
            f"Could not send email via SMTP ({_conf_plain(getattr(conf, 'MAIL_SERVER', None))}). "
            f"Check MAIL_* in .env, network/firewall, and spam folder. Details: {e}"
        ) from e

    logger.info("OTP email sent successfully to %s", to_email)
    if (os.getenv("MAIL_LOG_OTP") or "").strip().lower() in ("1", "true", "yes"):
        logger.warning("MAIL_LOG_OTP is on — OTP for %s: %s", to_email, otp)
