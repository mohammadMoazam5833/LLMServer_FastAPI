from __future__ import annotations

import base64
import logging
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.llm import RAGChunk, RAGFile

settings = get_settings()
logger = logging.getLogger(__name__)

SUPPORTED_TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".csv", ".json", ".py", ".c", ".cpp", ".h"}
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}

_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        import easyocr

        gpu = bool(settings.OCR_GPU)
        if gpu:
            try:
                import torch
                if not torch.cuda.is_available():
                    logger.warning("easyocr GPU requested but torch.cuda is not available; falling back to CPU")
                    gpu = False
            except Exception as exc:
                logger.warning("easyocr GPU requested but failed to import torch; falling back to CPU: %s", exc)
                gpu = False

        _reader = easyocr.Reader([settings.OCR_LANG or "fa", "en"], gpu=gpu)
        logger.info("easyocr Reader initialized with %s", "GPU" if gpu else "CPU")
    return _reader


def ocr_base64_image(base64_data: str) -> str:
    """OCR a base64-encoded image and return extracted text."""
    try:
        if "," in base64_data:
            base64_data = base64_data.split(",", 1)[1]
        image_bytes = base64.b64decode(base64_data)
        suffix = ".png"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name
        text = _extract_image_text(Path(tmp_path))
        os.unlink(tmp_path)
        return text.strip()
    except Exception as exc:
        logger.warning("OCR failed: %s", exc)
        return ""


def _safe_filename(filename: str) -> str:
    name = Path(filename or "upload.bin").name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


def _chunk_text(text: str) -> list[str]:
    size = max(settings.RAG_CHUNK_SIZE, 200)
    overlap = min(max(settings.RAG_CHUNK_OVERLAP, 0), size // 2)
    cleaned = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not cleaned:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(start + size, len(cleaned))
        chunks.append(cleaned[start:end].strip())
        if end == len(cleaned):
            break
        start = max(end - overlap, start + 1)
    return [chunk for chunk in chunks if chunk]


def _extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="PDF parsing requires pypdf. Install requirements before uploading PDFs.",
        ) from exc

    reader = PdfReader(str(path))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_image_text(path: Path) -> str:
    reader = _get_reader()
    results = reader.readtext(str(path))
    lines = [text for (_, text, conf) in results if conf > 0.3]
    return "\n".join(lines)


def extract_text(path: Path, content_type: str = "") -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf" or content_type == "application/pdf":
        return _extract_pdf_text(path)

    if suffix in SUPPORTED_IMAGE_SUFFIXES or content_type.startswith("image/"):
        return _extract_image_text(path)

    if suffix in SUPPORTED_TEXT_SUFFIXES or content_type.startswith("text/"):
        return path.read_text(encoding="utf-8", errors="ignore")

    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=f"Unsupported file type: {suffix or content_type or 'unknown'}",
    )


async def create_rag_file(
    db: AsyncSession,
    user_id: int,
    upload: UploadFile,
    process: bool = True,
) -> RAGFile:
    upload_dir = Path(settings.RAG_UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_id = uuid.uuid4()
    filename = _safe_filename(upload.filename or "upload.bin")
    path = upload_dir / f"{file_id}_{filename}"

    with path.open("wb") as out:
        shutil.copyfileobj(upload.file, out)

    rag_file = RAGFile(
        id=file_id,
        user_id=user_id,
        filename=filename,
        content_type=upload.content_type or "",
        path=str(path),
        status="uploaded",
    )
    db.add(rag_file)
    await db.flush()

    if process:
        await ingest_rag_file(db, rag_file)

    return rag_file


async def ingest_rag_file(db: AsyncSession, rag_file: RAGFile) -> RAGFile:
    try:
        text = extract_text(Path(rag_file.path), rag_file.content_type or "")
        chunks = _chunk_text(text)
        if not chunks:
            raise ValueError("No extractable text found in file")

        await db.execute(delete(RAGChunk).where(RAGChunk.file_id == rag_file.id))
        for index, chunk in enumerate(chunks):
            db.add(
                RAGChunk(
                    file_id=rag_file.id,
                    chunk_index=index,
                    content=chunk,
                    token_count=max(1, len(chunk.split())),
                )
            )

        rag_file.status = "ready"
        rag_file.error = ""
        rag_file.processed_at = datetime.now(timezone.utc)
        await db.flush()
        return rag_file
    except Exception as exc:
        rag_file.status = "failed"
        rag_file.error = str(exc)
        await db.flush()
        raise


async def list_rag_files(db: AsyncSession, user_id: int) -> list[dict]:
    result = await db.execute(
        select(RAGFile, func.count(RAGChunk.id).label("chunk_count"))
        .outerjoin(RAGChunk, RAGChunk.file_id == RAGFile.id)
        .where(RAGFile.user_id == user_id)
        .group_by(RAGFile.id)
        .order_by(RAGFile.created_at.desc())
    )
    return [
        {
            "id": rag_file.id,
            "filename": rag_file.filename,
            "content_type": rag_file.content_type,
            "status": rag_file.status,
            "created_at": rag_file.created_at,
            "chunk_count": chunk_count,
        }
        for rag_file, chunk_count in result.all()
    ]


def _score(query_terms: set[str], content: str) -> int:
    if not query_terms:
        return 0
    content_lower = content.lower()
    return sum(1 for term in query_terms if term in content_lower)


async def retrieve_context(
    db: AsyncSession,
    user_id: int,
    file_ids: list[uuid.UUID],
    query: str,
) -> str:
    if not file_ids:
        return ""

    result = await db.execute(
        select(RAGChunk, RAGFile.filename)
        .join(RAGFile, RAGFile.id == RAGChunk.file_id)
        .where(
            RAGFile.user_id == user_id,
            RAGFile.status == "ready",
            RAGFile.id.in_(file_ids),
        )
    )
    rows = result.all()
    query_terms = {term.lower() for term in re.findall(r"\w+", query or "") if len(term) > 2}
    ranked = sorted(
        ((chunk, filename, _score(query_terms, chunk.content)) for chunk, filename in rows),
        key=lambda item: item[2],
        reverse=True,
    )
    selected = [item for item in ranked if item[2] > 0][: settings.RAG_TOP_K]
    if not selected:
        logger.info("No relevant RAG chunks found for query; skipping context injection")
        return ""

    blocks = []
    for chunk, filename, _ in selected:
        blocks.append(f"[source: {filename}#{chunk.chunk_index}]\n{chunk.content}")

    return "\n\n".join(blocks)
