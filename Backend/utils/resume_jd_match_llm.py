"""Use OpenAI to score resume vs job description (ATS-style match)."""

import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from pathlib import Path

from openai import OpenAI

from database.models import JobDescription

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

MAX_RESUME_CHARS = int(os.getenv("RESUME_TEXT_MAX_CHARS_FOR_LLM", "24000"))


def _jd_text_bundle(jd: JobDescription) -> str:
    parts = [
        f"ROLE:\n{jd.role}",
        f"EXPERIENCE EXPECTED:\n{jd.experience}",
        f"REQUIREMENTS:\n{jd.requirements}",
        f"RESPONSIBILITIES:\n{jd.responsibilities}",
        f"QUALIFICATIONS:\n{jd.qualifications}",
        f"ELIGIBILITY:\n{jd.eligibility}",
    ]
    return "\n\n".join(parts)


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```\s*$", "", text)
    return json.loads(text)


def match_resume_to_jd_via_openai(resume_text: str, jd: JobDescription) -> dict[str, Any]:
    """
    Returns a dict with at least:
      ats_match_score (float 0-100), detailed_analysis, strengths_vs_jd, gaps_vs_jd,
      resume_summary
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not api_key.strip():
        raise ValueError("OPENAI_API_KEY is not configured")

    clipped = resume_text.strip()
    if len(clipped) > MAX_RESUME_CHARS:
        clipped = clipped[:MAX_RESUME_CHARS] + "\n\n[… resume truncated for analysis …]"

    jd_block = _jd_text_bundle(jd)
    model = os.getenv("OPENAI_MODEL", "gpt-4o")

    system = (
        "You are an expert technical recruiter and ATS analyst. "
        "Compare the candidate resume to the job description objectively. "
        "Output only valid JSON with these keys: "
        "ats_match_score (number 0-100, one decimal ok), "
        "detailed_analysis (string, markdown allowed: multi-paragraph assessment), "
        "strengths_vs_jd (string), gaps_vs_jd (string), "
        "resume_summary (string, 2-4 sentences on candidate background). "
        "Score reflects overall fit: skills, experience, education vs JD requirements."
    )
    user = (
        "JOB DESCRIPTION:\n"
        f"{jd_block}\n\n"
        "RESUME TEXT:\n"
        f"{clipped}"
    )

    client = OpenAI(api_key=api_key.strip())
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
    except Exception:
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
        )

    raw = completion.choices[0].message.content or ""
    data = _parse_json_object(raw)
    if not isinstance(data, dict):
        raise ValueError("Model did not return a JSON object")

    score_raw = data.get("ats_match_score", 0)
    try:
        score = float(score_raw)
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(100.0, score))

    return {
        "ats_match_score": score,
        "detailed_analysis": str(data.get("detailed_analysis") or "").strip() or "—",
        "strengths_vs_jd": str(data.get("strengths_vs_jd") or "").strip() or "—",
        "gaps_vs_jd": str(data.get("gaps_vs_jd") or "").strip() or "—",
        "resume_summary": str(data.get("resume_summary") or "").strip() or "—",
    }
