"""Business logic for email OTP and JWT issuance."""

import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from database.database import SessionLocal
from database.models import Users, generate_uuid
from modules.authentication.authentication_dto import OtpRequestDto, OtpVerifyDto
from utils.email_utils import send_otp_email
from utils.jwt_utils import create_access_token

logger = logging.getLogger(__name__)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _registration_complete(user: Optional[Users]) -> bool:
    """True after onboarding `/register` has set a password (fully registered)."""
    return bool(user and user.password_hash)


def _is_exist_int(user: Optional[Users]) -> int:
    return 1 if _registration_complete(user) else 0


def _persist_otp_for_existing_user(db: Session, email: str) -> tuple[Optional[str], Optional[str]]:
    """
    Set a new OTP only for an existing fully registered user.
    Returns (otp, error_message) or (None, None) on success.
    """
    user = db.query(Users).filter(Users.email == email).first()
    if not user:
        return None, "not_onboarded"
    if not _registration_complete(user):
        return None, "not_onboarded"
    otp = f"{secrets.randbelow(1000000):06d}"
    now = datetime.utcnow()
    user.otp = otp
    user.otp_created_at = now
    user.updated_at = now
    return otp, None


async def request_otp_unified_service(req: OtpRequestDto) -> dict:
    """
    Login only: send OTP if the email belongs to a fully onboarded user.
    Otherwise do **not** send an email; instruct the client to onboard first.
    """
    db: Session = SessionLocal()
    try:
        email = _normalize_email(str(req.email))
        if not email:
            return {"status": False, "message": "Email is required", "data": None}

        otp, err = _persist_otp_for_existing_user(db, email)
        if err == "not_onboarded":
            logger.info(
                "request-otp: no OTP for %s — user missing or onboarding incomplete "
                "(response status=false, is_exist=0; no email sent)",
                email,
            )
            return {
                "status": False,
                "message": "This email is not registered for login. Complete onboarding first using POST /api/onboarding/register.",
                "data": {"email": email, "is_exist": 0},
            }
        assert otp is not None
        logger.info("request-otp: sending SMTP to %s …", email)
        # Send before commit so we never claim success if SMTP fails.
        try:
            await send_otp_email(email, otp)
        except Exception as send_err:
            logger.error(
                "request-otp: SMTP failed for %s — %s (OTP not saved)",
                email,
                send_err,
            )
            db.rollback()
            return {
                "status": False,
                "message": str(send_err),
                "data": {"email": email, "is_exist": 1},
            }
        db.commit()
        logger.info(
            "request-otp: success for %s — OTP stored and SMTP reported OK "
            "(if inbox empty, check spam / recipient typo)",
            email,
        )
        return {
            "status": True,
            "message": "OTP sent to your email",
            "data": {"email": email, "is_exist": 1},
        }
    except Exception as e:
        db.rollback()
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()


def verify_otp_service(req: OtpVerifyDto) -> dict:
    db: Session = SessionLocal()
    try:
        email = _normalize_email(str(req.email))
        otp = req.otp.strip()

        user = db.query(Users).filter(Users.email == email).first()
        if not user:
            return {"status": False, "message": "Invalid or expired OTP", "data": None}
        if not _registration_complete(user):
            return {
                "status": False,
                "message": "Complete onboarding first using POST /api/onboarding/register.",
                "data": {"email": email, "is_exist": 0},
            }
        if not user.otp:
            return {"status": False, "message": "Invalid or expired OTP", "data": None}
        if user.otp != otp:
            return {"status": False, "message": "Invalid OTP", "data": None}
        if not user.otp_created_at:
            return {"status": False, "message": "Invalid OTP", "data": None}
        if datetime.utcnow() - user.otp_created_at > timedelta(minutes=5):
            return {"status": False, "message": "OTP expired", "data": None}

        user.otp = None
        user.otp_created_at = None
        user.email_verified = True
        user.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(user)

        token = create_access_token({"sub": user.id, "email": user.email})
        return {
            "status": True,
            "message": "OTP verified successfully",
            "data": {
                "access_token": token,
                "token_type": "bearer",
                "user_id": user.id,
                "is_exist": 1,
            },
        }
    except Exception as e:
        db.rollback()
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()
