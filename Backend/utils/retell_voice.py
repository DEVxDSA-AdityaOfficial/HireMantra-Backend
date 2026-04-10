"""Retell AI outbound call helpers."""

import os
from typing import Any, Optional

from dotenv import load_dotenv
from pathlib import Path

_env = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env)


def _client():
    from retell import Retell

    key = (os.getenv("RETELL_API_KEY") or "").strip()
    if not key:
        raise ValueError("RETELL_API_KEY is not configured")
    return Retell(api_key=key)


def start_screening_call(
    *,
    to_number: str,
    candidate_name: str,
    role_title: str,
    jd_excerpt: str,
    screening_minutes: str = "4",
) -> str:
    """
    Start outbound call. Returns retell call_id.
    Requires RETELL_FROM_NUMBER and RETELL_AGENT_ID in environment.
    """
    from_number = (os.getenv("RETELL_FROM_NUMBER") or "").strip()
    agent_id = (os.getenv("RETELL_AGENT_ID") or "").strip()
    if not from_number:
        raise ValueError("RETELL_FROM_NUMBER is not configured (your Retell-owned caller ID)")
    if not agent_id:
        raise ValueError("RETELL_AGENT_ID is not configured")

    client = _client()
    jd_short = (jd_excerpt or "")[:8000]
    try:
        resp = client.call.create_phone_call(
            from_number=from_number,
            to_number=to_number,
            override_agent_id=agent_id,
            retell_llm_dynamic_variables={
                "candidate_name": candidate_name,
                "role_title": role_title,
                "jd_context": jd_short,
                "screening_minutes": screening_minutes,
                "key_skills": role_title,
            },
        )
    except Exception as e:
        msg = str(e).lower()
        if "not found" in msg and "phone" in msg:
            raise ValueError(
                "RETELL_FROM_NUMBER is not a phone number on your Retell account. "
                "In the Retell dashboard, buy or connect a number, then set "
                "RETELL_FROM_NUMBER to that number in E.164 (e.g. +14155550100)."
            ) from e
        raise
    return str(resp.call_id)


def retrieve_call(call_id: str) -> dict[str, Any]:
    """Fetch call payload from Retell (transcript, duration, analysis)."""
    client = _client()
    call = client.call.retrieve(call_id)
    summary = ""
    if call.call_analysis:
        try:
            summary = str(call.call_analysis.call_summary or "")
        except Exception:
            summary = ""
    transcript = ""
    if call.transcript is not None:
        if isinstance(call.transcript, str):
            transcript = call.transcript
        else:
            transcript = str(call.transcript)
    dur = 0.0
    if call.duration_ms is not None:
        try:
            dur = float(call.duration_ms) / 1000.0
        except (TypeError, ValueError):
            dur = 0.0
    raw_status = getattr(call, "call_status", None)
    return {
        "call_id": call.call_id,
        "call_status": str(raw_status).lower() if raw_status is not None else "",
        "transcript": transcript,
        "duration_seconds": dur,
        "retell_summary": summary,
    }
