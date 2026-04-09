"""Business logic for AI-generated job descriptions (broadcasting)."""

from datetime import datetime

from sqlalchemy.orm import Session

from database.database import SessionLocal
from database.models import JobDescription, generate_uuid
from modules.Broadcasting.broadcasting_dto import GenerateJdDto, JobDescriptionUpdateDto
from utils.jd_llm_utils import generate_jd_fields_via_llm
from utils.organization_utils import get_organization_for_owner


def _serialize_jd(row: JobDescription) -> dict:
    return {
        "jd_id": row.id,
        "organization_id": row.organization_id,
        "created_by_user_id": row.created_by_user_id,
        "hr_query": row.hr_query,
        "role": row.role,
        "experience": row.experience,
        "requirements": row.requirements,
        "responsibilities": row.responsibilities,
        "qualifications": row.qualifications,
        "eligibility": row.eligibility,
        "application_link": row.application_link,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _organization_for_jd_or_error(db: Session, user_id: str) -> tuple[str | None, dict | None]:
    org = get_organization_for_owner(db, user_id)
    if not org:
        return None, {
            "status": False,
            "message": "Organization not found. Complete onboarding registration first.",
            "data": None,
        }
    return org.id, None


def generate_jd_service(user_id: str, req: GenerateJdDto) -> dict:
    db: Session = SessionLocal()
    try:
        org_id, err = _organization_for_jd_or_error(db, user_id)
        if err:
            return err

        try:
            fields = generate_jd_fields_via_llm(req.query)
        except Exception as e:
            return {"status": False, "message": str(e), "data": None}

        now = datetime.utcnow()
        jd_id = generate_uuid()
        row = JobDescription(
            id=jd_id,
            organization_id=org_id,
            created_by_user_id=user_id,
            hr_query=req.query.strip(),
            role=fields["role"],
            experience=fields["experience"],
            requirements=fields["requirements"],
            responsibilities=fields["responsibilities"],
            qualifications=fields["qualifications"],
            eligibility=fields["eligibility"],
            application_link=fields.get("application_link"),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        return {
            "status": True,
            "message": "Job description generated and saved",
            "data": _serialize_jd(row),
        }
    except Exception as e:
        db.rollback()
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()


def get_jd_service(user_id: str, jd_id: str) -> dict:
    db: Session = SessionLocal()
    try:
        org_id, err = _organization_for_jd_or_error(db, user_id)
        if err:
            return err

        row = db.query(JobDescription).filter(JobDescription.id == jd_id).first()
        if not row:
            return {"status": False, "message": "Job description not found", "data": None}
        if row.organization_id != org_id:
            return {"status": False, "message": "Forbidden", "data": None}
        return {"status": True, "message": "Success", "data": _serialize_jd(row)}
    except Exception as e:
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()


def update_jd_service(user_id: str, jd_id: str, req: JobDescriptionUpdateDto) -> dict:
    db: Session = SessionLocal()
    try:
        org_id, err = _organization_for_jd_or_error(db, user_id)
        if err:
            return err

        row = db.query(JobDescription).filter(JobDescription.id == jd_id).first()
        if not row:
            return {"status": False, "message": "Job description not found", "data": None}
        if row.organization_id != org_id:
            return {"status": False, "message": "Forbidden", "data": None}

        for field in (
            "role",
            "experience",
            "requirements",
            "responsibilities",
            "qualifications",
            "eligibility",
            "application_link",
            "hr_query",
        ):
            value = getattr(req, field, None)
            if value is None:
                continue
            if field == "application_link":
                v = value.strip() if isinstance(value, str) else str(value)
                setattr(row, field, v if v else None)
            elif field in (
                "requirements",
                "responsibilities",
                "qualifications",
                "eligibility",
                "hr_query",
            ):
                setattr(row, field, value)
            else:
                setattr(row, field, value.strip() if isinstance(value, str) else value)

        row.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(row)

        return {
            "status": True,
            "message": "Job description updated",
            "data": _serialize_jd(row),
        }
    except Exception as e:
        db.rollback()
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()


def delete_jd_service(user_id: str, jd_id: str) -> dict:
    db: Session = SessionLocal()
    try:
        org_id, err = _organization_for_jd_or_error(db, user_id)
        if err:
            return err

        row = db.query(JobDescription).filter(JobDescription.id == jd_id).first()
        if not row:
            return {"status": False, "message": "Job description not found", "data": None}
        if row.organization_id != org_id:
            return {"status": False, "message": "Forbidden", "data": None}
        db.delete(row)
        db.commit()
        return {"status": True, "message": "Job description deleted", "data": {"jd_id": jd_id}}
    except Exception as e:
        db.rollback()
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()
