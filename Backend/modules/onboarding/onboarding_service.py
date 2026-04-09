"""Business logic for onboarding registration and CRUD."""

from datetime import datetime

from sqlalchemy.orm import Session

from database.database import SessionLocal
from database.models import Onboarding, Organization, Users, generate_uuid
from modules.onboarding.onboarding_dto import (
    OnboardingRegisterDto,
    OnboardingUpdateDto,
)
from utils.organization_utils import get_organization_for_owner
from utils.password_utils import hash_password


def _serialize_onboarding(user: Users, org: Organization, row: Onboarding) -> dict:
    return {
        "id": row.id,
        "organization_id": org.id,
        "owner_user_id": org.owner_user_id,
        "email": user.email,
        "member_name": row.member_name,
        "organization_name": row.organization_name,
        "contact": row.contact,
        "address": row.address,
        "team_size": row.team_size,
        "website": row.website,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def complete_registration_service(user_id: str, req: OnboardingRegisterDto) -> dict:
    db: Session = SessionLocal()
    try:
        user = db.query(Users).filter(Users.id == user_id).first()
        if not user:
            return {"status": False, "message": "User not found", "data": None}
        if not user.email_verified:
            return {"status": False, "message": "Email not verified", "data": None}

        if get_organization_for_owner(db, user_id):
            return {
                "status": False,
                "message": "Registration already completed",
                "data": None,
            }

        now = datetime.utcnow()
        user.password_hash = hash_password(req.password)
        user.updated_at = now

        org = Organization(
            id=generate_uuid(),
            owner_user_id=user_id,
            created_at=now,
            updated_at=now,
        )
        db.add(org)
        db.flush()

        row = Onboarding(
            id=generate_uuid(),
            organization_id=org.id,
            member_name=req.member_name.strip(),
            organization_name=req.organization_name.strip(),
            contact=req.contact.strip(),
            address=req.address.strip(),
            team_size=req.team_size.strip(),
            website=req.website.strip() if req.website else None,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(org)
        db.refresh(row)

        return {
            "status": True,
            "message": "Registration completed successfully",
            "data": _serialize_onboarding(user, org, row),
        }
    except Exception as e:
        db.rollback()
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()


def get_onboarding_service(user_id: str) -> dict:
    db: Session = SessionLocal()
    try:
        user = db.query(Users).filter(Users.id == user_id).first()
        if not user:
            return {"status": False, "message": "User not found", "data": None}
        org = get_organization_for_owner(db, user_id)
        if not org:
            return {"status": False, "message": "Onboarding record not found", "data": None}
        row = db.query(Onboarding).filter(Onboarding.organization_id == org.id).first()
        if not row:
            return {"status": False, "message": "Onboarding record not found", "data": None}
        return {
            "status": True,
            "message": "Success",
            "data": _serialize_onboarding(user, org, row),
        }
    except Exception as e:
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()


def update_onboarding_service(user_id: str, req: OnboardingUpdateDto) -> dict:
    db: Session = SessionLocal()
    try:
        user = db.query(Users).filter(Users.id == user_id).first()
        if not user:
            return {"status": False, "message": "User not found", "data": None}
        org = get_organization_for_owner(db, user_id)
        if not org:
            return {"status": False, "message": "Onboarding record not found", "data": None}
        row = db.query(Onboarding).filter(Onboarding.organization_id == org.id).first()
        if not row:
            return {"status": False, "message": "Onboarding record not found", "data": None}

        for field in (
            "member_name",
            "organization_name",
            "contact",
            "address",
            "team_size",
            "website",
        ):
            value = getattr(req, field, None)
            if value is not None:
                if isinstance(value, str) and field != "address":
                    value = value.strip()
                setattr(row, field, value)

        row.updated_at = datetime.utcnow()
        org.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(row)

        return {
            "status": True,
            "message": "Onboarding updated",
            "data": _serialize_onboarding(user, org, row),
        }
    except Exception as e:
        db.rollback()
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()


def delete_onboarding_service(user_id: str) -> dict:
    db: Session = SessionLocal()
    try:
        org = get_organization_for_owner(db, user_id)
        if not org:
            return {"status": False, "message": "Onboarding record not found", "data": None}
        oid = org.id
        db.delete(org)
        db.commit()
        return {
            "status": True,
            "message": "Organization and related data removed",
            "data": {"organization_id": oid},
        }
    except Exception as e:
        db.rollback()
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()
