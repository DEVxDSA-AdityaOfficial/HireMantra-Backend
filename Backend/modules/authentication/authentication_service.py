"""Business logic for email OTP and JWT issuance."""

import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from database.database import SessionLocal
from database.models import Users, generate_uuid
from modules.authentication.authentication_dto import OtpRequestDto, OtpVerifyDto
from utils.email_utils import send_otp_email
from utils.jwt_utils import create_access_token


def _normalize_email(email: str) -> str:
    return email.strip().lower()


async def request_otp_service(req: OtpRequestDto) -> dict:
    db: Session = SessionLocal()
    try:
        email = _normalize_email(str(req.email))
        if not email:
            return {"status": False, "message": "Email is required", "data": None}

        otp = f"{secrets.randbelow(1000000):06d}"
        now = datetime.utcnow()

        user = db.query(Users).filter(Users.email == email).first()
        if user:
            user.otp = otp
            user.otp_created_at = now
            user.updated_at = now
        else:
            user = Users(
                id=generate_uuid(),
                email=email,
                password_hash=None,
                otp=otp,
                otp_created_at=now,
                email_verified=False,
                created_at=now,
                updated_at=now,
            )
            db.add(user)

        db.commit()
        await send_otp_email(email, otp)
        return {
            "status": True,
            "message": "OTP sent to your email",
            "data": {"email": email},
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
        if not user or not user.otp:
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

        token = create_access_token({"sub": user.id, "email": user.email})
        return {
            "status": True,
            "message": "OTP verified successfully",
            "data": {
                "access_token": token,
                "token_type": "bearer",
                "user_id": user.id,
            },
        }
    except Exception as e:
        db.rollback()
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()
