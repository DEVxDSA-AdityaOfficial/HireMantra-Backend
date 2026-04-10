"""Extract plain text from resume files (PDF, DOCX)."""

from pathlib import Path


def extract_text_from_resume_file(path: Path) -> str:
    """
    Read resume bytes from disk and return UTF-8 text.
    Raises ValueError with a clear message for unsupported or empty extraction.
    """
    path = path.resolve()
    if not path.is_file():
        raise ValueError("Resume file not found")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    if suffix == ".doc":
        raise ValueError(
            "Legacy .doc format is not supported; please upload PDF or DOCX."
        )
    raise ValueError(f"Unsupported resume format: {suffix or '(none)'}")


def _extract_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    text = "\n".join(parts).strip()
    if not text:
        raise ValueError("Could not extract text from PDF (file may be image-only).")
    return text


def _extract_docx(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    parts = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
    text = "\n".join(parts).strip()
    if not text:
        raise ValueError("Could not extract text from DOCX.")
    return text
