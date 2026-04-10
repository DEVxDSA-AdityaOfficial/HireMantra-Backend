"""Employer communications: shortlist/rejection email, Retell voice screen, scoring."""

import json
import os
from datetime import datetime
from typing import Any, Optional, Tuple

from sqlalchemy.orm import Session

from database.database import SessionLocal
from database.models import (
    Candidate,
    CandidateNotification,
    JobDescription,
    Onboarding,
    VoiceInterviewSession,
    generate_uuid,
)
from modules.communication.communication_dto import (
    ScheduleVoiceInterviewDto,
    SendRejectionEmailDto,
    SendShortlistEmailDto,
)
from utils.communication_mail import send_html_email
from utils.interview_score_llm import score_voice_interview_transcript
from utils.organization_utils import get_organization_for_owner
from utils.phone_utils import to_e164
from utils.retell_voice import retrieve_call, start_screening_call


def _env_subject(key: str, default: str) -> str:
    v = (os.getenv(key) or "").strip()
    return v or default


def _screening_minutes() -> int:
    try:
        return int(os.getenv("VOICE_SCREENING_TARGET_MINUTES", "4"))
    except ValueError:
        return 4


def _default_country() -> str:
    return (os.getenv("PHONE_DEFAULT_COUNTRY_CODE", "91") or "91").strip().lstrip("+")


def _employer_candidate_bundle(
    db: Session, user_id: str, candidate_id: str
) -> Tuple[Optional[tuple], Optional[dict]]:
    org = get_organization_for_owner(db, user_id)
    if not org:
        return None, {
            "status": False,
            "message": "Organization not found. Complete onboarding first.",
            "data": None,
        }
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        return None, {"status": False, "message": "Candidate not found", "data": None}
    jd = (
        db.query(JobDescription)
        .filter(JobDescription.id == candidate.job_description_id)
        .first()
    )
    if not jd or jd.organization_id != org.id:
        return None, {"status": False, "message": "Forbidden", "data": None}
    onboarding = (
        db.query(Onboarding).filter(Onboarding.organization_id == org.id).first()
    )
    brand = onboarding.organization_name if onboarding else "Our team"
    return (candidate, jd, brand), None


def _resolve_email(candidate: Candidate, override: Optional[str]) -> Optional[str]:
    if override and str(override).strip():
        return str(override).strip().lower()
    if candidate.email and candidate.email.strip():
        return candidate.email.strip().lower()
    return None


def _role_title(jd: JobDescription) -> str:
    t = (jd.role or "").strip()
    return (t.split("\n")[0][:200]) if t else "Open role"


async def send_shortlist_email_service(
    user_id: str, candidate_id: str, req: SendShortlistEmailDto
) -> dict:
    db: Session = SessionLocal()
    try:
        bundle, err = _employer_candidate_bundle(db, user_id, candidate_id)
        if err:
            return err
        assert bundle is not None
        candidate, jd, brand = bundle
        if (candidate.screening_status or "") != "shortlisted":
            return {
                "status": False,
                "message": "Candidate must be shortlisted before sending shortlist email.",
                "data": None,
            }
        to_email = _resolve_email(candidate, req.to_email)
        if not to_email:
            return {
                "status": False,
                "message": "No email on file. Pass to_email or set candidate.email.",
                "data": None,
            }
        subject = _env_subject(
            "EMAIL_SHORTLIST_SUBJECT",
            "Congratulations — you have been shortlisted",
        )
        note = (req.extra_note or "").strip()
        note_html = f"<p>{note}</p>" if note else ""
        body = f"""
        <p>Hi {candidate.full_name},</p>
        <p><strong>{brand}</strong> has shortlisted you for the role: <strong>{_role_title(jd)}</strong>.</p>
        {note_html}
        <p>We will be in touch with next steps.</p>
        <p>— {brand}</p>
        """
        nid = generate_uuid()
        row = CandidateNotification(
            id=nid,
            candidate_id=candidate.id,
            notification_type="shortlist",
            to_email=to_email,
            subject=subject,
            body_html=body,
            status="pending",
            created_by_user_id=user_id,
            created_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        try:
            await send_html_email(to_email=to_email, subject=subject, body_html=body)
            row.status = "sent"
            row.sent_at = datetime.utcnow()
            if req.to_email:
                candidate.email = to_email
            candidate.updated_at = datetime.utcnow()
            db.commit()
        except Exception as e:
            row.status = "failed"
            row.error_message = str(e)
            db.commit()
            return {
                "status": False,
                "message": str(e),
                "data": {"notification_id": row.id},
            }
        return {
            "status": True,
            "message": "Shortlist email sent",
            "data": {"notification_id": row.id, "to_email": to_email},
        }
    except Exception as e:
        db.rollback()
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()


async def send_rejection_email_service(
    user_id: str, candidate_id: str, req: SendRejectionEmailDto
) -> dict:
    db: Session = SessionLocal()
    try:
        bundle, err = _employer_candidate_bundle(db, user_id, candidate_id)
        if err:
            return err
        assert bundle is not None
        candidate, jd, brand = bundle
        if (candidate.screening_status or "") != "rejected":
            return {
                "status": False,
                "message": "Candidate must be in rejected status for this template.",
                "data": None,
            }
        to_email = _resolve_email(candidate, req.to_email)
        if not to_email:
            return {
                "status": False,
                "message": "No email on file. Pass to_email or set candidate.email.",
                "data": None,
            }
        subject = _env_subject(
            "EMAIL_REJECTION_SUBJECT",
            "Thank you for your application",
        )
        note = (req.extra_note or "").strip()
        note_html = f"<p>{note}</p>" if note else ""
        body = f"""
        <p>Hi {candidate.full_name},</p>
        <p>Thank you for your interest in <strong>{_role_title(jd)}</strong> at <strong>{brand}</strong>.</p>
        <p>We will not be moving forward with your application at this time.</p>
        {note_html}
        <p>We appreciate the time you invested and wish you success in your search.</p>
        <p>— {brand}</p>
        """
        nid = generate_uuid()
        row = CandidateNotification(
            id=nid,
            candidate_id=candidate.id,
            notification_type="rejection",
            to_email=to_email,
            subject=subject,
            body_html=body,
            status="pending",
            created_by_user_id=user_id,
            created_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        try:
            await send_html_email(to_email=to_email, subject=subject, body_html=body)
            row.status = "sent"
            row.sent_at = datetime.utcnow()
            if req.to_email:
                candidate.email = to_email
            candidate.updated_at = datetime.utcnow()
            db.commit()
        except Exception as e:
            row.status = "failed"
            row.error_message = str(e)
            db.commit()
            return {
                "status": False,
                "message": str(e),
                "data": {"notification_id": row.id},
            }
        return {
            "status": True,
            "message": "Rejection email sent",
            "data": {"notification_id": row.id, "to_email": to_email},
        }
    except Exception as e:
        db.rollback()
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()


async def _send_interview_invite_email(
    db: Session,
    *,
    user_id: str,
    candidate: Candidate,
    jd: JobDescription,
    brand: str,
    to_email: str,
    extra_note: Optional[str],
) -> None:
    subject = _env_subject(
        "EMAIL_INTERVIEW_SUBJECT",
        "Interview — AI screening call scheduled",
    )
    note = (extra_note or "").strip()
    note_html = f"<p>{note}</p>" if note else ""
    body = f"""
    <p>Hi {candidate.full_name},</p>
    <p><strong>{brand}</strong> would like to conduct a short AI-assisted phone screening
    (about {_screening_minutes()} minutes) for <strong>{_role_title(jd)}</strong>.</p>
    {note_html}
    <p>Please be available to answer a call at the phone number we have on file.</p>
    <p>— {brand}</p>
    """
    nid = generate_uuid()
    row = CandidateNotification(
        id=nid,
        candidate_id=candidate.id,
        notification_type="interview_invite",
        to_email=to_email,
        subject=subject,
        body_html=body,
        status="pending",
        created_by_user_id=user_id,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    await send_html_email(to_email=to_email, subject=subject, body_html=body)
    row.status = "sent"
    row.sent_at = datetime.utcnow()


def _fail_voice_session(session_id: str, message: str) -> None:
    db = SessionLocal()
    try:
        row = (
            db.query(VoiceInterviewSession)
            .filter(VoiceInterviewSession.id == session_id)
            .first()
        )
        if row:
            row.status = "failed"
            row.error_message = message
            row.updated_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


async def schedule_voice_interview_service(
    user_id: str, candidate_id: str, req: ScheduleVoiceInterviewDto
) -> dict:
    db: Session = SessionLocal()
    sid: str
    phone: str
    candidate_name: str
    role_title_for_call: str = ""
    jd_excerpt_for_call: str = ""
    try:
        bundle, err = _employer_candidate_bundle(db, user_id, candidate_id)
        if err:
            return err
        assert bundle is not None
        candidate, jd, brand = bundle
        if (candidate.screening_status or "") != "shortlisted":
            return {
                "status": False,
                "message": "Only shortlisted candidates can be scheduled for a voice interview.",
                "data": None,
            }
        raw_phone = (req.to_number or "").strip() or candidate.contact_phone
        try:
            phone = to_e164(raw_phone, _default_country())
        except ValueError as e:
            return {"status": False, "message": str(e), "data": None}

        now = datetime.utcnow()
        sid = generate_uuid()
        session = VoiceInterviewSession(
            id=sid,
            candidate_id=candidate.id,
            created_by_user_id=user_id,
            retell_call_id=None,
            from_number=(os.getenv("RETELL_FROM_NUMBER") or "").strip() or None,
            to_number=phone,
            status="scheduled",
            scheduled_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(session)
        db.commit()
        candidate_name = (candidate.full_name or "").strip()
        role_title_for_call = _role_title(jd)
        jd_excerpt_for_call = "\n".join(
            [
                jd.role or "",
                jd.requirements or "",
                jd.responsibilities or "",
            ]
        )[:8000]

        if req.send_interview_invite_email:
            invite_email = _resolve_email(candidate, req.invite_to_email)
            if not invite_email:
                _fail_voice_session(
                    sid,
                    "send_interview_invite_email requires invite_to_email or candidate.email",
                )
                return {
                    "status": False,
                    "message": "send_interview_invite_email requires invite_to_email or candidate.email",
                    "data": {"session_id": sid},
                }
            try:
                await _send_interview_invite_email(
                    db,
                    user_id=user_id,
                    candidate=candidate,
                    jd=jd,
                    brand=brand,
                    to_email=invite_email,
                    extra_note=req.invite_extra_note,
                )
                db.commit()
            except Exception as e:
                db.rollback()
                _fail_voice_session(sid, f"Invite email failed: {e}")
                return {
                    "status": False,
                    "message": str(e),
                    "data": {"session_id": sid},
                }
    except Exception as e:
        db.rollback()
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()

    try:
        call_id = start_screening_call(
            to_number=phone,
            candidate_name=candidate_name,
            role_title=role_title_for_call,
            jd_excerpt=jd_excerpt_for_call,
            screening_minutes=str(_screening_minutes()),
        )
    except Exception as e:
        _fail_voice_session(sid, str(e))
        return {
            "status": False,
            "message": str(e),
            "data": {"session_id": sid},
        }

    db2: Session = SessionLocal()
    try:
        row = (
            db2.query(VoiceInterviewSession)
            .filter(VoiceInterviewSession.id == sid)
            .first()
        )
        if not row or row.status == "failed":
            return {
                "status": False,
                "message": "Session aborted",
                "data": {"session_id": sid},
            }
        row.retell_call_id = call_id
        row.status = "dialing"
        row.updated_at = datetime.utcnow()
        db2.commit()
        return {
            "status": True,
            "message": "Voice interview call initiated",
            "data": {
                "session_id": row.id,
                "retell_call_id": row.retell_call_id,
                "to_number": phone,
                "status": row.status,
            },
        }
    except Exception as e:
        db2.rollback()
        _fail_voice_session(sid, str(e))
        return {
            "status": False,
            "message": str(e),
            "data": {"session_id": sid},
        }
    finally:
        db2.close()


def _session_for_employer(
    db: Session, user_id: str, session_id: str
) -> Tuple[Optional[VoiceInterviewSession], Optional[dict]]:
    org = get_organization_for_owner(db, user_id)
    if not org:
        return None, {
            "status": False,
            "message": "Organization not found.",
            "data": None,
        }
    session = (
        db.query(VoiceInterviewSession)
        .filter(VoiceInterviewSession.id == session_id)
        .first()
    )
    if not session:
        return None, {"status": False, "message": "Session not found", "data": None}
    cand = db.query(Candidate).filter(Candidate.id == session.candidate_id).first()
    if not cand:
        return None, {"status": False, "message": "Candidate not found", "data": None}
    jd = (
        db.query(JobDescription)
        .filter(JobDescription.id == cand.job_description_id)
        .first()
    )
    if not jd or jd.organization_id != org.id:
        return None, {"status": False, "message": "Forbidden", "data": None}
    return session, None


def _serialize_session(
    s: VoiceInterviewSession, *, include_transcript: bool = True
) -> dict[str, Any]:
    details = None
    if s.interview_details_json:
        try:
            details = json.loads(s.interview_details_json)
        except json.JSONDecodeError:
            details = None
    t = s.transcript or ""
    if include_transcript:
        transcript_out = t or None
    else:
        transcript_out = (t[:500] + "…") if len(t) > 500 else (t or None)
    return {
        "session_id": s.id,
        "candidate_id": s.candidate_id,
        "retell_call_id": s.retell_call_id,
        "from_number": s.from_number,
        "to_number": s.to_number,
        "status": s.status,
        "duration_seconds": s.duration_seconds,
        "interview_score": s.interview_score,
        "interview_analysis": s.interview_analysis,
        "interview_details": details,
        "retell_summary": s.retell_summary,
        "transcript": transcript_out,
        "scheduled_at": s.scheduled_at.isoformat() if s.scheduled_at else None,
        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        "error_message": s.error_message,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def sync_voice_interview_service(user_id: str, session_id: str) -> dict:
    db: Session = SessionLocal()
    try:
        session, err = _session_for_employer(db, user_id, session_id)
        if err:
            return err
        assert session is not None
        if not session.retell_call_id:
            return {
                "status": False,
                "message": "No Retell call id on this session.",
                "data": None,
            }
        cand = db.query(Candidate).filter(Candidate.id == session.candidate_id).first()
        jd = (
            db.query(JobDescription)
            .filter(JobDescription.id == cand.job_description_id)
            .first()
        )
        assert jd is not None

        try:
            payload = retrieve_call(session.retell_call_id)
        except Exception as e:
            session.error_message = str(e)
            session.updated_at = datetime.utcnow()
            db.commit()
            return {"status": False, "message": str(e), "data": None}

        transcript = (payload.get("transcript") or "").strip()
        dur = float(payload.get("duration_seconds") or 0)
        summary = (payload.get("retell_summary") or "").strip()
        call_status = str(payload.get("call_status") or "").lower()

        session.transcript = payload.get("transcript") or ""
        session.duration_seconds = dur
        session.retell_summary = summary or None
        session.updated_at = datetime.utcnow()

        if call_status in ("ongoing", "ringing", "registered"):
            db.commit()
            return {
                "status": True,
                "message": "Call still in progress; try sync again later.",
                "data": _serialize_session(session),
            }

        session.completed_at = datetime.utcnow()
        if not transcript:
            session.status = "completed"
            session.interview_score = None
            session.interview_analysis = "No transcript available yet."
            db.commit()
            return {
                "status": True,
                "message": "Call completed but transcript empty.",
                "data": _serialize_session(session),
            }

        try:
            scored = score_voice_interview_transcript(
                jd, transcript, screening_minutes=_screening_minutes()
            )
        except Exception as e:
            session.status = "completed"
            session.error_message = f"Scoring failed: {e}"
            db.commit()
            return {
                "status": False,
                "message": str(e),
                "data": _serialize_session(session),
            }

        session.status = "scored"
        session.interview_score = scored["interview_score"]
        session.interview_analysis = scored["detailed_analysis"]
        session.interview_details_json = json.dumps(
            {
                "strengths": scored["strengths"],
                "improvements": scored["improvements"],
                "jd_alignment_notes": scored["jd_alignment_notes"],
                "min_match_percentage": float(os.getenv("MIN_MATCH_PERCENTAGE", "60")),
            },
            ensure_ascii=False,
        )
        db.commit()
        db.refresh(session)
        return {
            "status": True,
            "message": "Transcript synced and interview scored",
            "data": _serialize_session(session),
        }
    except Exception as e:
        db.rollback()
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()


def list_voice_interviews_service(user_id: str, candidate_id: Optional[str]) -> dict:
    db: Session = SessionLocal()
    try:
        org = get_organization_for_owner(db, user_id)
        if not org:
            return {
                "status": False,
                "message": "Organization not found.",
                "data": None,
            }
        q = (
            db.query(VoiceInterviewSession)
            .join(Candidate, VoiceInterviewSession.candidate_id == Candidate.id)
            .join(JobDescription, Candidate.job_description_id == JobDescription.id)
            .filter(JobDescription.organization_id == org.id)
        )
        if candidate_id:
            q = q.filter(VoiceInterviewSession.candidate_id == candidate_id)
        rows = q.order_by(VoiceInterviewSession.created_at.desc()).all()
        return {
            "status": True,
            "message": "Success",
            "data": {
                "sessions": [
                    _serialize_session(r, include_transcript=False) for r in rows
                ]
            },
        }
    except Exception as e:
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()


def get_voice_interview_service(user_id: str, session_id: str) -> dict:
    db: Session = SessionLocal()
    try:
        session, err = _session_for_employer(db, user_id, session_id)
        if err:
            return err
        assert session is not None
        return {
            "status": True,
            "message": "Success",
            "data": _serialize_session(session),
        }
    except Exception as e:
        return {"status": False, "message": str(e), "data": None}
    finally:
        db.close()
