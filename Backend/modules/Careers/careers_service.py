"""Public careers listings, applications, and employer views."""

import json
from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from database.database import SessionLocal
from database.models import Candidate, JobDescription, Organization, generate_uuid
from utils.organization_utils import get_organization_for_owner
from utils.resume_storage import absolute_resume_path, save_resume_file


def _serialize_jd_public(row: JobDescription) -> dict:
    return {
        "jd_id": row.id,
        "organization_id": row.organization_id,
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


def _serialize_candidate(row: Candidate) -> dict:
    details = None
    if row.screening_details_json:
        try:
            details = json.loads(row.screening_details_json)
        except json.JSONDecodeError:
            details = None
    return {
        "id": row.id,
        "jd_id": row.job_description_id,
        "name": row.full_name,
        "email": row.email,
        "contact": row.contact_phone,
        "resume_filename": row.resume_original_filename,
        "screening_status": row.screening_status or "pending",
        "ats_match_score": row.ats_match_score,
        "jd_match_analysis": row.jd_match_analysis,
        "screening_details": details,
        "parsed_resume_summary": row.parsed_resume_summary,
        "parser_error_message": row.parser_error_message,
        "screening_updated_at": row.screening_updated_at.isoformat()
        if row.screening_updated_at
        else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def list_job_descriptions_for_organization_service(organization_id: str) -> dict:
    db: Session = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.id == organization_id).first()
        if not org:
            return {"status": False, "message": "Organization not found", "data": None}
        rows = (
            db.query(JobDescription)
            .filter(JobDescription.organization_id == organization_id)
            .order_by(JobDescription.created_at.desc())
            .all()
        )
        return {
            "status": True,
            "message": "Success",
            "data": {"organization_id": organization_id, "jobs": [_serialize_jd_public(r) for r in rows]},
        }
    except Exception as e:
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()


def get_public_job_description_service(organization_id: str, jd_id: str) -> dict:
    db: Session = SessionLocal()
    try:
        row = db.query(JobDescription).filter(JobDescription.id == jd_id).first()
        if not row or row.organization_id != organization_id:
            return {"status": False, "message": "Job description not found", "data": None}
        return {
            "status": True,
            "message": "Success",
            "data": _serialize_jd_public(row),
        }
    except Exception as e:
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()


def apply_for_job_service(
    jd_id: str,
    name: str,
    contact: str,
    resume_content: bytes,
    resume_filename: str,
) -> dict:
    db: Session = SessionLocal()
    rel_path: Optional[str] = None
    try:
        jd = db.query(JobDescription).filter(JobDescription.id == jd_id).first()
        if not jd:
            return {"status": False, "message": "Job description not found", "data": None}

        full_name = name.strip()
        phone = contact.strip()
        if not full_name:
            return {"status": False, "message": "Name is required", "data": None}
        if not phone:
            return {"status": False, "message": "Contact number is required", "data": None}

        candidate_id = generate_uuid()
        try:
            rel_path, orig_safe = save_resume_file(
                candidate_id, resume_filename or "resume.pdf", resume_content
            )
        except ValueError as e:
            return {"status": False, "message": str(e), "data": None}

        now = datetime.utcnow()
        row = Candidate(
            id=candidate_id,
            job_description_id=jd_id,
            full_name=full_name,
            contact_phone=phone,
            resume_relative_path=rel_path,
            resume_original_filename=orig_safe,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        return {
            "status": True,
            "message": "Application submitted successfully",
            "data": _serialize_candidate(row),
        }
    except Exception as e:
        db.rollback()
        if rel_path:
            try:
                p = absolute_resume_path(rel_path)
                if p.is_file():
                    p.unlink()
            except Exception:
                pass
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()


def _candidate_for_org_user(
    db: Session, user_id: str, candidate_id: str
) -> Tuple[Optional[Candidate], Optional[dict]]:
    org = get_organization_for_owner(db, user_id)
    if not org:
        return None, {
            "status": False,
            "message": "Organization not found. Complete onboarding registration first.",
            "data": None,
        }
    row = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not row:
        return None, {"status": False, "message": "Application not found", "data": None}
    jd = db.query(JobDescription).filter(JobDescription.id == row.job_description_id).first()
    if not jd or jd.organization_id != org.id:
        return None, {"status": False, "message": "Forbidden", "data": None}
    return row, None


def list_applications_for_employer_service(user_id: str, jd_id: Optional[str]) -> dict:
    db: Session = SessionLocal()
    try:
        org = get_organization_for_owner(db, user_id)
        if not org:
            return {
                "status": False,
                "message": "Organization not found. Complete onboarding registration first.",
                "data": None,
            }
        q = (
            db.query(Candidate)
            .join(JobDescription, Candidate.job_description_id == JobDescription.id)
            .filter(JobDescription.organization_id == org.id)
        )
        if jd_id:
            q = q.filter(Candidate.job_description_id == jd_id)
        rows = q.order_by(Candidate.created_at.desc()).all()
        return {
            "status": True,
            "message": "Success",
            "data": {"applications": [_serialize_candidate(r) for r in rows]},
        }
    except Exception as e:
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()


def get_application_for_employer_service(user_id: str, candidate_id: str) -> dict:
    db: Session = SessionLocal()
    try:
        row, err = _candidate_for_org_user(db, user_id, candidate_id)
        if err:
            return err
        assert row is not None
        return {
            "status": True,
            "message": "Success",
            "data": _serialize_candidate(row),
        }
    except Exception as e:
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()


def resume_download_for_employer(
    user_id: str, candidate_id: str
) -> Tuple[Optional[str], Optional[str], Optional[dict]]:
    """
    Return (absolute_path, suggested_download_filename, error_envelope).
    error_envelope is set iff path is None.
    """
    db: Session = SessionLocal()
    try:
        row, err = _candidate_for_org_user(db, user_id, candidate_id)
        if err:
            return None, None, err
        assert row is not None
        try:
            path = absolute_resume_path(row.resume_relative_path)
        except ValueError as e:
            return None, None, {"status": False, "message": str(e), "data": None}
        if not path.is_file():
            return None, None, {
                "status": False,
                "message": "Resume file not found on disk",
                "data": None,
            }
        return str(path), row.resume_original_filename, None
    finally:
        db.close()
