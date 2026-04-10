"""Screen candidates: extract resume text, OpenAI vs JD, update status and scores."""

import json
import os
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from database.database import SessionLocal
from database.models import Candidate, JobDescription
from modules.Careers.careers_service import _candidate_for_org_user
from utils.resume_jd_match_llm import match_resume_to_jd_via_openai
from utils.resume_storage import absolute_resume_path
from utils.resume_text_extract import extract_text_from_resume_file

SHORTLIST_THRESHOLD = float(os.getenv("ATS_SHORTLIST_THRESHOLD", "60"))


def _serialize_screening(row: Candidate) -> dict[str, Any]:
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
        "contact": row.contact_phone,
        "resume_filename": row.resume_original_filename,
        "screening_status": row.screening_status,
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


def _run_screening_core(db: Session, row: Candidate, jd: JobDescription) -> dict:
    """Mutates row in memory; caller commits. Returns API envelope dict."""
    now = datetime.utcnow()
    try:
        path = absolute_resume_path(row.resume_relative_path)
        resume_text = extract_text_from_resume_file(path)
    except ValueError as e:
        row.screening_status = "parsing_failed"
        row.parser_error_message = str(e)
        row.ats_match_score = None
        row.jd_match_analysis = None
        row.screening_details_json = None
        row.parsed_resume_summary = None
        row.screening_updated_at = now
        row.updated_at = now
        return {
            "status": True,
            "message": "Screening completed (resume could not be parsed)",
            "data": _serialize_screening(row),
        }

    if len(resume_text.strip()) < 40:
        row.screening_status = "parsing_failed"
        row.parser_error_message = "Extracted resume text is too short to analyze."
        row.ats_match_score = None
        row.jd_match_analysis = None
        row.screening_details_json = None
        row.parsed_resume_summary = None
        row.screening_updated_at = now
        row.updated_at = now
        return {
            "status": True,
            "message": "Screening completed (insufficient resume text)",
            "data": _serialize_screening(row),
        }

    try:
        llm = match_resume_to_jd_via_openai(resume_text, jd)
    except Exception as e:
        row.screening_status = "parsing_failed"
        row.parser_error_message = str(e)
        row.ats_match_score = None
        row.jd_match_analysis = None
        row.screening_details_json = None
        row.parsed_resume_summary = None
        row.screening_updated_at = now
        row.updated_at = now
        return {
            "status": True,
            "message": "Screening completed (AI analysis failed)",
            "data": _serialize_screening(row),
        }

    score = float(llm["ats_match_score"])
    status = "shortlisted" if score >= SHORTLIST_THRESHOLD else "rejected"

    details_payload = {
        "strengths_vs_jd": llm["strengths_vs_jd"],
        "gaps_vs_jd": llm["gaps_vs_jd"],
        "ats_shortlist_threshold": SHORTLIST_THRESHOLD,
    }

    row.screening_status = status
    row.ats_match_score = score
    row.jd_match_analysis = llm["detailed_analysis"]
    row.screening_details_json = json.dumps(details_payload, ensure_ascii=False)
    row.parsed_resume_summary = llm["resume_summary"]
    row.parser_error_message = None
    row.screening_updated_at = now
    row.updated_at = now

    return {
        "status": True,
        "message": f"Screening complete: {status.replace('_', ' ')}",
        "data": _serialize_screening(row),
    }


def analyze_candidate_for_employer(user_id: str, candidate_id: str) -> dict:
    db: Session = SessionLocal()
    try:
        row, err = _candidate_for_org_user(db, user_id, candidate_id)
        if err:
            return err
        assert row is not None
        jd = (
            db.query(JobDescription)
            .filter(JobDescription.id == row.job_description_id)
            .first()
        )
        if not jd:
            return {"status": False, "message": "Job description not found", "data": None}

        out = _run_screening_core(db, row, jd)
        db.commit()
        db.refresh(row)
        return out
    except Exception as e:
        db.rollback()
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()


def run_screening_for_candidate_id(candidate_id: str) -> None:
    """
    Background job after public apply: no employer user context.
    Only updates rows that exist; ignores unknown ids.
    """
    db: Session = SessionLocal()
    try:
        row = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not row:
            return
        jd = (
            db.query(JobDescription)
            .filter(JobDescription.id == row.job_description_id)
            .first()
        )
        if not jd:
            return
        _run_screening_core(db, row, jd)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def schedule_candidate_screening(candidate_id: str) -> None:
    """Entry point for FastAPI BackgroundTasks."""
    run_screening_for_candidate_id(candidate_id)
