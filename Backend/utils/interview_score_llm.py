"""OpenAI: score voice interview transcript vs JD."""

import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from database.models import JobDescription

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

_PROMPT_PATH = _ROOT / "prompts" / "voice_interview_score.txt"


def _jd_bundle(jd: JobDescription) -> str:
    return "\n\n".join(
        [
            f"ROLE:\n{jd.role}",
            f"EXPERIENCE:\n{jd.experience}",
            f"REQUIREMENTS:\n{jd.requirements}",
            f"RESPONSIBILITIES:\n{jd.responsibilities}",
        ]
    )


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```\s*$", "", text)
    return json.loads(text)


def score_voice_interview_transcript(
    jd: JobDescription,
    transcript: str,
    screening_minutes: int = 4,
) -> dict[str, Any]:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not configured")

    template = _PROMPT_PATH.read_text(encoding="utf-8")
    user_block = template.format(screening_minutes=screening_minutes)
    jd_text = _jd_bundle(jd)
    model = os.getenv("OPENAI_MODEL", "gpt-4o")

    client = OpenAI(api_key=api_key)
    messages = [
        {
            "role": "system",
            "content": "You output only valid JSON per the user instructions.",
        },
        {
            "role": "user",
            "content": f"{user_block}\n\nJOB DESCRIPTION:\n{jd_text}\n\nCALL TRANSCRIPT:\n{transcript}",
        },
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
    score_raw = data.get("interview_score", 0)
    try:
        score = float(score_raw)
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(100.0, score))
    return {
        "interview_score": score,
        "detailed_analysis": str(data.get("detailed_analysis") or "").strip() or "—",
        "strengths": str(data.get("strengths") or "").strip() or "—",
        "improvements": str(data.get("improvements") or "").strip() or "—",
        "jd_alignment_notes": str(data.get("jd_alignment_notes") or "").strip() or "—",
    }
