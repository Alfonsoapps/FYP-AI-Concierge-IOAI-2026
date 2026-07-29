"""
Upload Service

Centralised file handling for the AI Concierge chatbot.
Responsibilities:
    - Validate uploaded files (extension, MIME type, size)
    - Save files to a temporary directory
    - Extract text content from PDF, DOCX, and TXT files
    - Prepare image uploads (PNG, JPG, JPEG, GIF, WEBP) for future vision support
    - Clean up temporary files after processing

Design notes:
    - All file I/O is async-friendly (uses awaitable UploadFile reads)
    - Text extraction is synchronous but fast for typical document sizes
    - Fail-soft: extraction errors return an empty string with a logged warning
    - The service does NOT call the AI pipeline — it only prepares data for it
"""

import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS: set[str] = {
    ".pdf", ".docx", ".doc", ".txt",
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
}

TEXT_EXTENSIONS: set[str] = {".pdf", ".docx", ".doc", ".txt"}
IMAGE_EXTENSIONS: set[str] = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

ALLOWED_MIME_PREFIXES: set[str] = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "image/",
}

MAX_FILE_SIZE_MB: int = 10
MAX_FILE_SIZE_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024

UPLOAD_DIR: Path = Path(__file__).resolve().parents[1] / "data" / "uploads"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class UploadResult:
    """Result of processing an uploaded file."""

    filename: str
    saved_path: Path
    extension: str
    size_bytes: int
    is_image: bool = False
    extracted_text: str = ""
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_file(file: UploadFile) -> str:
    """
    Validate an uploaded file's filename, extension, and MIME type.

    Returns:
        The normalised lowercase file extension (e.g. ".pdf").

    Raises:
        HTTPException 400 if the file is invalid.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file has no filename.")

    ext = os.path.splitext(file.filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{ext}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )

    # MIME type check (content_type may be None for some clients)
    if file.content_type:
        mime_ok = any(
            file.content_type == allowed or file.content_type.startswith(allowed)
            for allowed in ALLOWED_MIME_PREFIXES
        )
        if not mime_ok:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported MIME type '{file.content_type}' for file '{file.filename}'.",
            )

    return ext


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

async def save_file(file: UploadFile) -> tuple[Path, int]:
    """
    Save an uploaded file to the temporary uploads directory.

    Returns:
        A tuple of (saved_path, size_in_bytes).

    Raises:
        HTTPException 413 if the file exceeds the size limit.
    """
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    unique_name = f"{uuid.uuid4().hex}_{file.filename}"
    dest = UPLOAD_DIR / unique_name

    total_bytes = 0
    chunk_size = 64 * 1024  # 64 KB

    with open(dest, "wb") as f:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > MAX_FILE_SIZE_BYTES:
                f.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large. Maximum size is {MAX_FILE_SIZE_MB} MB.",
                )
            f.write(chunk)

    logger.info("Saved upload: %s (%d KB)", unique_name, total_bytes // 1024)
    return dest, total_bytes


# ---------------------------------------------------------------------------
# Text Extraction
# ---------------------------------------------------------------------------

def extract_text_from_pdf(file_path: Path) -> str:
    """Extract text from a PDF file using pypdf."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(file_path))
        pages_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text.strip())

        full_text = "\n\n".join(pages_text)
        logger.info("Extracted %d chars from PDF (%d pages)", len(full_text), len(reader.pages))
        return full_text

    except ImportError:
        logger.warning("pypdf not installed — cannot extract PDF text.")
        return ""
    except Exception as exc:
        logger.warning("PDF text extraction failed for %s: %s", file_path.name, exc)
        return ""


def extract_text_from_docx(file_path: Path) -> str:
    """Extract text from a DOCX file using python-docx."""
    try:
        from docx import Document

        doc = Document(str(file_path))
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        full_text = "\n\n".join(paragraphs)
        logger.info("Extracted %d chars from DOCX (%d paragraphs)", len(full_text), len(paragraphs))
        return full_text

    except ImportError:
        logger.warning("python-docx not installed — cannot extract DOCX text.")
        return ""
    except Exception as exc:
        logger.warning("DOCX text extraction failed for %s: %s", file_path.name, exc)
        return ""


def extract_text_from_txt(file_path: Path) -> str:
    """Read plain text from a .txt file."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        logger.info("Read %d chars from TXT file", len(text))
        return text.strip()
    except Exception as exc:
        logger.warning("TXT read failed for %s: %s", file_path.name, exc)
        return ""


def extract_text(file_path: Path, extension: str) -> str:
    """
    Route text extraction to the appropriate handler based on extension.

    Returns:
        Extracted text content, or empty string if extraction fails or
        the file type doesn't support text extraction (e.g. images).
    """
    if extension == ".pdf":
        return extract_text_from_pdf(file_path)
    elif extension in (".docx", ".doc"):
        return extract_text_from_docx(file_path)
    elif extension == ".txt":
        return extract_text_from_txt(file_path)
    else:
        # Images and unsupported types — no text to extract
        return ""


# ---------------------------------------------------------------------------
# Image preparation (for future vision model support)
# ---------------------------------------------------------------------------

def prepare_image(file_path: Path, extension: str) -> dict:
    """
    Prepare an image file for future vision model processing.

    Returns a metadata dict with the file path and basic info.
    This is a placeholder — actual vision processing will be added later.
    """
    import imghdr

    metadata = {
        "type": "image",
        "path": str(file_path),
        "extension": extension,
        "size_bytes": file_path.stat().st_size,
        "ready_for_vision": True,
    }

    # Attempt to detect actual image format for extra validation
    try:
        detected = imghdr.what(str(file_path))
        metadata["detected_format"] = detected
    except Exception:
        metadata["detected_format"] = None

    logger.info("Image prepared for vision: %s (%s)", file_path.name, extension)
    return metadata


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def delete_temp_file(file_path: Path) -> None:
    """Delete a temporary upload file. Fails silently if already gone."""
    try:
        if file_path.exists():
            file_path.unlink()
            logger.debug("Deleted temp file: %s", file_path.name)
    except OSError as exc:
        logger.warning("Could not delete temp file %s: %s", file_path.name, exc)


# ---------------------------------------------------------------------------
# Main entry point: process_upload()
# ---------------------------------------------------------------------------

async def process_upload(file: UploadFile) -> UploadResult:
    """
    Full upload pipeline: validate → save → extract/prepare → return result.

    This is the primary function callers should use. It:
        1. Validates the file (extension, MIME, filename)
        2. Saves it to a temp directory (enforcing size limit)
        3. Extracts text (PDF/DOCX/TXT) or prepares image metadata
        4. Returns an UploadResult with all extracted data

    The caller is responsible for calling delete_temp_file() when done.
    """
    # Step 1: Validate
    ext = validate_file(file)

    # Step 2: Save
    saved_path, size_bytes = await save_file(file)

    # Step 3: Extract or prepare
    is_image = ext in IMAGE_EXTENSIONS
    extracted_text = ""
    metadata: dict = {}

    if is_image:
        metadata = prepare_image(saved_path, ext)
    else:
        extracted_text = extract_text(saved_path, ext)

    # Build result
    result = UploadResult(
        filename=file.filename or "unknown",
        saved_path=saved_path,
        extension=ext,
        size_bytes=size_bytes,
        is_image=is_image,
        extracted_text=extracted_text,
        metadata=metadata,
    )

    logger.info(
        "Upload processed: %s | %s | %d KB | text=%d chars | image=%s",
        result.filename,
        result.extension,
        result.size_bytes // 1024,
        len(result.extracted_text),
        result.is_image,
    )

    return result
