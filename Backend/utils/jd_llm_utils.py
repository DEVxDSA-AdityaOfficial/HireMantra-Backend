"""Load JD prompt template and call OpenAI to produce structured JSON."""

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

JD_PROMPT_PATH = _ROOT / "prompts" / "JD.txt"

REQUIRED_JD_KEYS = (
    "role",
    "experience",
    "requirements",
    "responsibilities",
    "qualifications",
    "eligibility",
    "application_link",
)


def _load_prompt_template() -> str:
    return JD_PROMPT_PATH.read_text(encoding="utf-8")


def build_jd_system_user_messages(hr_query: str) -> tuple[str, str]:
    """Return (system_instruction, user_content) for chat completion."""
    template = _load_prompt_template()
    user_content = template.replace("{hr_query}", hr_query.strip())
    system = (
        "You follow instructions exactly. Output only valid JSON as specified by the user message."
    )
    return system, user_content


def _parse_json_object(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```\s*$", "", text)
    return json.loads(text)


def _normalize_jd_payload(data: dict) -> dict:
    out: dict = {}
    for key in REQUIRED_JD_KEYS:
        val = data.get(key)
        if key == "application_link":
            out[key] = None if val in (None, "", "null") else str(val).strip()
            continue
        if val is None or (isinstance(val, str) and not val.strip()):
            out[key] = "—"
        else:
            out[key] = str(val).strip()
    return out


def generate_jd_fields_via_llm(hr_query: str) -> dict:
    """
    Call OpenAI Chat Completions; return normalized dict with REQUIRED_JD_KEYS.
    Raises on API or parse errors.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not api_key.strip():
        raise ValueError("OPENAI_API_KEY is not configured")

    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    system, user_content = build_jd_system_user_messages(hr_query)

    client = OpenAI(api_key=api_key.strip())
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.4,
            response_format={"type": "json_object"},
        )
    except Exception:
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.4,
        )
    raw = completion.choices[0].message.content or ""
    parsed = _parse_json_object(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Model did not return a JSON object")
    return _normalize_jd_payload(parsed)
