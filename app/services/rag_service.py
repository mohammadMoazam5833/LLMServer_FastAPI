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
from app.services.token_utils import estimate_text_tokens

settings = get_settings()
logger = logging.getLogger(__name__)

_rag_vectorizer = None


def _get_rag_vectorizer():
    global _rag_vectorizer
    if _rag_vectorizer is None:
        from sklearn.feature_extraction.text import HashingVectorizer

        _rag_vectorizer = HashingVectorizer(
            n_features=settings.RAG_EMBEDDING_DIM,
            alternate_sign=False,
            norm="l2",
            ngram_range=(1, 2),
            analyzer="word",
            token_pattern=r"\w+",
        )
    return _rag_vectorizer


def _embed_text(text: str) -> list[float]:
    if not text:
        return []
    vectorizer = _get_rag_vectorizer()
    embedding = vectorizer.transform([text]).toarray()[0]
    return embedding.tolist()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))

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

        embedding_list = [_embed_text(chunk) for chunk in chunks]
        for index, (chunk, embedding) in enumerate(zip(chunks, embedding_list)):
            db.add(
                RAGChunk(
                    file_id=rag_file.id,
                    chunk_index=index,
                    content=chunk,
                    token_count=max(1, len(chunk.split())),
                    metadata_={"embedding": embedding},
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


def _score(query_terms: set[str], content: str) -> tuple[float, int]:
    if not query_terms:
        return 0.0, 0
    content_terms = {term.lower() for term in re.findall(r"\w+", content or "") if len(term) > 2}
    match_count = sum(1 for term in query_terms if term in content_terms)
    score = match_count / len(query_terms) if query_terms else 0.0
    return score, match_count


async def retrieve_context(
    db: AsyncSession,
    user_id: int,
    file_ids: list[uuid.UUID],
    query: str,
) -> str:
    if not file_ids:
        return ""

    query_terms = {term.lower() for term in re.findall(r"\w+", query or "") if len(term) > 2}
    if not query_terms:
        logger.info("Empty or too short query for RAG retrieval; skipping context injection")
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
    chunk_embeddings = []
    for chunk, filename in rows:
        embedding = None
        if chunk.metadata_ and isinstance(chunk.metadata_, dict):
            embedding = chunk.metadata_.get("embedding")
        if isinstance(embedding, list) and len(embedding) == settings.RAG_EMBEDDING_DIM:
            chunk_embeddings.append((chunk, filename, embedding))

    ranked = []
    if chunk_embeddings:
        query_embedding = _embed_text(query)
        if not query_embedding or sum(abs(x) for x in query_embedding) == 0:
            logger.info("Query embedding is empty; skipping semantic RAG retrieval")
            return ""
        ranked = sorted(
            (
                (
                    chunk,
                    filename,
                    max(
                        _cosine_similarity(query_embedding, embedding),
                        _score(query_terms, chunk.content)[0],
                    ),
                )
                for chunk, filename, embedding in chunk_embeddings
            ),
            key=lambda item: item[2],
            reverse=True,
        )
        logger.info("Using semantic+lexical retrieval for RAG context; candidate chunks=%d", len(ranked))
    else:
        ranked = sorted(
            ((chunk, filename, *_score(query_terms, chunk.content)) for chunk, filename in rows),
            key=lambda item: item[2],
            reverse=True,
        )
        logger.info("No semantic embeddings available; falling back to lexical retrieval")

    min_score = settings.RAG_MIN_SCORE
    if len(query_terms) <= 3:
        min_score = max(min_score, 0.5)

    selected = [item for item in ranked if item[2] >= min_score][: settings.RAG_TOP_K]
    if not selected:
        logger.info(
            "No RAG chunk passed min_score=%.2f for query with %d terms; skipping context injection",
            min_score,
            len(query_terms),
        )
        return ""

    max_context_tokens = settings.RAG_MAX_CONTEXT_TOKENS
    tokens = 0
    blocks = []
    for chunk, filename, score in selected:
        chunk_tokens = estimate_text_tokens(chunk.content)
        if tokens + chunk_tokens > max_context_tokens:
            logger.info(
                "RAG context token limit reached: %d/%d tokens; stopping selection",
                tokens,
                max_context_tokens,
            )
            break
        blocks.append(f"[source: {filename}#{chunk.chunk_index}]\n{chunk.content}")
        tokens += chunk_tokens

    if not blocks:
        logger.info(
            "Relevant RAG chunks exist but none fit within %d token budget; skipping context injection",
            max_context_tokens,
        )
        return ""

    logger.info(
        "Selected %d RAG chunks with min_score=%.2f and total_context_tokens=%d",
        len(blocks),
        min_score,
        tokens,
    )
    return "\n\n".join(blocks)
