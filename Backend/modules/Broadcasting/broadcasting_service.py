"""Business logic for AI-generated job descriptions (broadcasting)."""

import os
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from database.database import SessionLocal
from database.models import JobDescription, generate_uuid
from modules.Broadcasting.broadcasting_dto import (
    CreateBroadcastPostStructureDto,
    GenerateBroadcastMediaDto,
    GenerateJdDto,
    JobDescriptionUpdateDto,
)
from utils.gemini_broadcast import (
    build_media_prompt_from_jd,
    generate_channel_post_structures,
    generate_job_promo_image_bytes,
    generate_job_promo_video_file,
    jd_to_prompt_context,
)
from utils.jd_llm_utils import generate_jd_fields_via_llm
from utils.organization_utils import get_organization_for_owner

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

# Clearer than generic "Forbidden" when JWT org ≠ JD.organization_id
MSG_JD_WRONG_ORG = (
    "This job description does not belong to your organization. "
    "Use a jd_id from your account (GET /api/broadcasting/job-descriptions)."
)


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
            return {"status": False, "message": MSG_JD_WRONG_ORG, "data": None}
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
            return {"status": False, "message": MSG_JD_WRONG_ORG, "data": None}

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


def _jd_row_for_org(
    db: Session, user_id: str, jd_id: str
) -> tuple[JobDescription | None, dict | None]:
    org_id, err = _organization_for_jd_or_error(db, user_id)
    if err:
        return None, err
    row = db.query(JobDescription).filter(JobDescription.id == jd_id).first()
    if not row:
        return None, {"status": False, "message": "Job description not found", "data": None}
    if row.organization_id != org_id:
        return None, {"status": False, "message": MSG_JD_WRONG_ORG, "data": None}
    return row, None


def list_job_descriptions_service(user_id: str) -> dict:
    """All JDs for the authenticated user's organization."""
    db: Session = SessionLocal()
    try:
        org_id, err = _organization_for_jd_or_error(db, user_id)
        if err:
            return err
        rows = (
            db.query(JobDescription)
            .filter(JobDescription.organization_id == org_id)
            .order_by(JobDescription.created_at.desc())
            .all()
        )
        return {
            "status": True,
            "message": "Success",
            "data": {"job_descriptions": [_serialize_jd(r) for r in rows]},
        }
    except Exception as e:
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()


def create_broadcast_post_structure_service(
    user_id: str, jd_id: str, req: CreateBroadcastPostStructureDto
) -> dict:
    """Gemini text: LinkedIn + Unstop style post skeletons from JD."""
    db: Session = SessionLocal()
    try:
        row, err = _jd_row_for_org(db, user_id, jd_id)
        if err:
            return err
        assert row is not None
        ctx = jd_to_prompt_context(row)
        try:
            structures = generate_channel_post_structures(
                ctx, channels=req.channels
            )
        except Exception as e:
            return {"status": False, "message": str(e), "data": None}
        return {
            "status": True,
            "message": "Post structures generated",
            "data": {
                "jd_id": jd_id,
                "channels_requested": req.channels,
                "post_structures": structures,
            },
        }
    except Exception as e:
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()


def generate_broadcast_media_service(
    user_id: str, jd_id: str, req: GenerateBroadcastMediaDto
) -> dict:
    """Gemini image or Veo video saved under data/broadcast_media/{org}/{jd}/."""
    db: Session = SessionLocal()
    try:
        row, err = _jd_row_for_org(db, user_id, jd_id)
        if err:
            return err
        assert row is not None
        org_id = row.organization_id
        ctx = jd_to_prompt_context(row)
        creative_brief = None
        if req.use_structure_creative_brief:
            try:
                st = generate_channel_post_structures(
                    ctx, channels=["linkedin", "unstop"]
                )
                if isinstance(st, dict):
                    creative_brief = st.get("creative_brief_for_media")
                    if isinstance(creative_brief, str):
                        creative_brief = creative_brief.strip() or None
            except Exception as e:
                return {
                    "status": False,
                    "message": f"Could not build structure brief: {e}",
                    "data": None,
                }

        prompt = build_media_prompt_from_jd(
            ctx,
            content_kind=req.content_type,
            extra=req.extra_context,
            creative_brief=creative_brief,
        )

        media_root = Path(
            os.getenv("BROADCAST_MEDIA_DIR", "./data/broadcast_media")
        ).resolve()
        out_dir = (media_root / org_id / jd_id).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        file_id = generate_uuid()
        mime_out: str

        if req.content_type == "image":
            try:
                blob, mime = generate_job_promo_image_bytes(prompt)
            except Exception as e:
                return {"status": False, "message": str(e), "data": None}
            ext = "png"
            if "jpeg" in mime or "jpg" in mime:
                ext = "jpg"
            out_path = out_dir / f"{file_id}.{ext}"
            out_path.write_bytes(blob)
            mime_out = "image/jpeg" if ext == "jpg" else "image/png"
        else:
            out_path = out_dir / f"{file_id}.mp4"
            try:
                generate_job_promo_video_file(
                    prompt,
                    aspect_ratio=(req.aspect_ratio or "9:16"),
                    output_path=out_path,
                    poll_interval_seconds=req.poll_interval_seconds,
                    max_wait_seconds=req.max_wait_seconds,
                )
            except Exception as e:
                return {"status": False, "message": str(e), "data": None}
            mime_out = "video/mp4"

        try:
            rel = str(out_path.relative_to(_BACKEND_ROOT))
        except ValueError:
            rel = str(out_path)

        return {
            "status": True,
            "message": "Media generated",
            "data": {
                "jd_id": jd_id,
                "content_type": req.content_type,
                "mime_type": mime_out,
                "relative_path": rel,
                "prompt_preview": prompt[:800],
            },
        }
    except Exception as e:
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
            return {"status": False, "message": MSG_JD_WRONG_ORG, "data": None}
        db.delete(row)
        db.commit()
        return {"status": True, "message": "Job description deleted", "data": {"jd_id": jd_id}}
    except Exception as e:
        db.rollback()
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()
