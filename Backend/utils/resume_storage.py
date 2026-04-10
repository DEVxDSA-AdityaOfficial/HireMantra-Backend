"""Save applicant resumes under a configurable upload directory."""

import os
import re
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

ALLOWED_EXTENSIONS = frozenset({".pdf", ".doc", ".docx"})
MAX_RESUME_BYTES = int(os.getenv("MAX_RESUME_UPLOAD_BYTES", str(10 * 1024 * 1024)))


def resume_upload_root() -> Path:
    raw = os.getenv("RESUME_UPLOAD_DIR", str(_ROOT / "uploads" / "resumes"))
    return Path(raw).expanduser().resolve()


def safe_original_filename(name: str) -> str:
    base = Path(name or "resume").name
    base = re.sub(r"[^\w.\-]", "_", base, flags=re.UNICODE)
    if not base or base in (".", ".."):
        base = "resume"
    return base[:200]


def save_resume_file(candidate_id: str, original_filename: str, content: bytes) -> tuple[str, str]:
    """
    Write bytes to disk. Returns (resume_relative_path, stored_original_filename).
    Relative path is relative to resume_upload_root() parent... Actually we store
    path relative to upload root: "resumes/<candidate_id>_<file>".
    """
    if len(content) > MAX_RESUME_BYTES:
        raise ValueError(
            f"Resume exceeds maximum size of {MAX_RESUME_BYTES // (1024 * 1024)} MB"
        )

    safe_name = safe_original_filename(original_filename)
    ext = Path(safe_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Resume must be a .pdf, .doc, or .docx file")

    root = resume_upload_root()
    root.mkdir(parents=True, exist_ok=True)

    stored_name = f"{candidate_id}_{safe_name}"
    dest = root / stored_name
    dest.write_bytes(content)
    rel = stored_name
    return rel, safe_name


def absolute_resume_path(relative_stored_name: str) -> Path:
    """Resolve DB-stored relative filename to an absolute path under upload root."""
    rel = Path(relative_stored_name).name
    path = resume_upload_root() / rel
    resolved = path.resolve()
    root = resume_upload_root()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError("Invalid resume path") from None
    return resolved
