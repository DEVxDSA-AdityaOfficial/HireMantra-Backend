"""Google Gemini / Veo helpers for broadcast post copy and media generation."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")


def _normalize_gemini_model_id(raw: str) -> str:
    """
    Strip ``models/`` prefix and fix common ``.env`` typo ``emini-...`` → ``gemini-...``.
    Google's 404 often shows ``models/emini-...`` when the leading ``g`` was dropped.
    """
    n = (raw or "").strip()
    if n.lower().startswith("models/"):
        n = n[7:].strip()
    if n.startswith("emini-"):
        logger.warning(
            "Model id looks like a typo (missing leading 'g'): fixed %r → %r",
            raw,
            "g" + n,
        )
        return "g" + n
    return n


def _api_key() -> str:
    return (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()


def _text_model() -> str:
    return _normalize_gemini_model_id(
        (os.getenv("GEMINI_TEXT_MODEL") or "gemini-2.0-flash").strip()
    )


def _image_model() -> str:
    return _normalize_gemini_model_id(
        (os.getenv("GEMINI_IMAGE_MODEL") or "gemini-2.5-flash-image").strip()
    )


def _video_model() -> str:
    return _normalize_gemini_model_id(
        (os.getenv("GEMINI_VIDEO_MODEL") or "veo-3.1-generate-preview").strip()
    )


def _genai_client():
    from google import genai

    key = _api_key()
    if not key:
        raise ValueError(
            "Set GOOGLE_API_KEY or GEMINI_API_KEY in .env for Gemini / Veo APIs."
        )
    return genai.Client(api_key=key)


def jd_to_prompt_context(row: Any) -> str:
    """Flatten a JobDescription ORM row into text for prompts."""
    parts = [
        f"ROLE:\n{getattr(row, 'role', '') or ''}",
        f"EXPERIENCE:\n{getattr(row, 'experience', '') or ''}",
        f"REQUIREMENTS:\n{getattr(row, 'requirements', '') or ''}",
        f"RESPONSIBILITIES:\n{getattr(row, 'responsibilities', '') or ''}",
        f"QUALIFICATIONS:\n{getattr(row, 'qualifications', '') or ''}",
        f"ELIGIBILITY:\n{getattr(row, 'eligibility', '') or ''}",
        f"APPLICATION_LINK:\n{getattr(row, 'application_link', '') or ''}",
    ]
    return "\n\n".join(parts)


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```\s*$", "", text)
    return json.loads(text)


def generate_channel_post_structures(
    jd_context: str,
    *,
    channels: list[str] | None = None,
) -> dict[str, Any]:
    """
    Ask Gemini for channel-specific post skeletons (LinkedIn, Unstop).
    Returns a dict with at least ``linkedin`` and ``unstop`` keys when requested.
    """
    channels = channels or ["linkedin", "unstop"]
    ch_lower = [c.lower().strip() for c in channels]

    schema_hint = """
Return ONLY valid JSON (no markdown) with this exact top-level shape:
{
  "linkedin": {
    "headline": "string, punchy, <= 200 chars",
    "primary_text": "string, main post with \\n for line breaks",
    "hashtags": ["string"],
    "call_to_action": "string",
    "suggested_first_comment": "string optional"
  },
  "unstop": {
    "title": "string, event-style title",
    "tagline": "string, one line hook",
    "description_plain": "string, 2-4 short paragraphs plain text",
    "tags": ["string"],
    "prize_or_perks_line": "string optional",
    "cta_text": "string"
  },
  "creative_brief_for_media": "string, one paragraph visual direction for image/video prompts"
}
Include "linkedin" only if linkedin is in the channel list; same for unstop.
If a channel is omitted, use null for that key.
"""
    user = (
        f"Channels to fill: {', '.join(ch_lower)}.\n\n"
        f"JOB DESCRIPTION:\n{jd_context}\n\n{schema_hint}"
    )

    client = _genai_client()
    full = (
        "You are a social recruiting copywriter. "
        "Respond with ONLY a single JSON object, no markdown fences.\n\n"
        + user
    )
    resp = client.models.generate_content(
        model=_text_model(),
        contents=full,
    )

    text_out = ""
    try:
        if resp.candidates and resp.candidates[0].content.parts:
            for p in resp.candidates[0].content.parts:
                if getattr(p, "text", None):
                    text_out += p.text
    except Exception:
        text_out = str(resp)

    if not text_out.strip():
        raise ValueError("Gemini returned empty text for post structures")

    return _parse_json_object(text_out)


def generate_job_promo_image_bytes(
    prompt: str,
) -> tuple[bytes, str]:
    """Returns (image_bytes, mime_type)."""
    from google.genai import types

    client = _genai_client()
    model = _image_model()
    response = None
    last_err: Exception | None = None

    # Image-capable models often require response_modalities on the Gemini API.
    for attempt in ("modalities", "plain"):
        try:
            if attempt == "modalities":
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE", "TEXT"],
                    ),
                )
            else:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                )
            break
        except Exception as e:
            last_err = e
            response = None
            if attempt == "plain":
                raise last_err from None

    if response is None:
        raise last_err or RuntimeError("No response from image model")

    if not response.candidates:
        raise ValueError("No candidates in image response")

    for part in response.candidates[0].content.parts:
        inline = getattr(part, "inline_data", None)
        if inline is not None and getattr(inline, "data", None):
            data = inline.data
            if isinstance(data, bytes):
                return data, getattr(inline, "mime_type", None) or "image/png"
            raw = bytes(data) if data is not None else b""
            return raw, getattr(inline, "mime_type", None) or "image/png"

    raise ValueError(
        "Image response had no inline_data parts. "
        "Try GEMINI_IMAGE_MODEL=gemini-2.0-flash-preview-image-generation or "
        "gemini-2.5-flash-image (check spelling: must start with gemini-)."
    )


def generate_job_promo_video_file(
    prompt: str,
    *,
    aspect_ratio: str = "9:16",
    output_path: Path,
    poll_interval_seconds: float = 10.0,
    max_wait_seconds: float = 600.0,
) -> Path:
    """
    Run Veo text-to-video; poll until done or timeout. Writes MP4 to ``output_path``.
    """
    from google.genai import types

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    client = _genai_client()
    model = _video_model()

    operation = client.models.generate_videos(
        model=model,
        prompt=prompt,
        config=types.GenerateVideosConfig(
            aspect_ratio=aspect_ratio,
        ),
    )

    deadline = time.monotonic() + max_wait_seconds
    while not operation.done:
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"Video generation exceeded {max_wait_seconds}s; try again or increase "
                "max_wait_seconds / GEMINI_VIDEO_POLL settings."
            )
        logger.info("Veo: waiting for video (model=%s)...", model)
        time.sleep(poll_interval_seconds)
        operation = client.operations.get(operation)

    if getattr(operation, "error", None):
        raise RuntimeError(f"Veo operation failed: {operation.error}")

    resp = operation.response
    if not resp or not getattr(resp, "generated_videos", None):
        raise ValueError("Veo response missing generated_videos")

    generated = resp.generated_videos[0]
    video = generated.video

    if hasattr(client, "files") and hasattr(client.files, "download"):
        client.files.download(file=video)

    if hasattr(video, "save"):
        video.save(str(output_path))
    else:
        raise RuntimeError(
            "SDK video object has no .save(); upgrade google-genai or adjust download path."
        )

    return output_path


def build_media_prompt_from_jd(
    jd_context: str,
    *,
    content_kind: str,
    extra: str | None = None,
    creative_brief: str | None = None,
) -> str:
    """Single prompt for Veo / image model from JD text."""
    base = (
        f"Professional, upbeat recruiting and employer-branding {content_kind} for a job opening. "
        "Diverse inclusive workplace, modern office or abstract tech career visuals, "
        "no misleading company logos, no real brand names unless generic.\n\n"
        f"JOB CONTEXT:\n{jd_context[:12000]}"
    )
    if creative_brief:
        base += f"\n\nCREATIVE DIRECTION:\n{creative_brief[:2000]}"
    if extra:
        base += f"\n\nEXTRA:\n{extra[:2000]}"
    if content_kind == "video":
        base += (
            "\n\nCinematic short clip suitable for social (LinkedIn / Unstop style), "
            "high energy, subtle motion, professional color grade."
        )
    return base
