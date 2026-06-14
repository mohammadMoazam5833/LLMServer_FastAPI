# from __future__ import annotations
#
# import base64
# import logging
# import os
# import re
# import shutil
# import tempfile
# import uuid
# import asyncio
# from datetime import datetime, timezone
# from pathlib import Path
# import hashlib
# import httpx
#
# from fastapi import HTTPException, UploadFile, status
# from sqlalchemy import delete, func, select
# from sqlalchemy.ext.asyncio import AsyncSession
#
# from app.config import get_settings
# from app.models.llm import RAGChunk, RAGFile
# from app.services.token_utils import estimate_text_tokens
#
# settings = get_settings()
# logger = logging.getLogger(__name__)
#
# _rag_vectorizer = None
# _reader = None
# _reader_lock = asyncio.Lock()  # قفل برای جلوگیری از لود همزمان مدل روی GPU
#
#
# def _get_rag_vectorizer():
#     global _rag_vectorizer
#     if _rag_vectorizer is None:
#         from sklearn.feature_extraction.text import HashingVectorizer
#
#         _rag_vectorizer = HashingVectorizer(
#             n_features=settings.RAG_EMBEDDING_DIM,
#             alternate_sign=False,
#             norm="l2",
#             ngram_range=(1, 2),
#             analyzer="word",
#             token_pattern=r"\w+",
#         )
#     return _rag_vectorizer
#
#
# def _embed_text(text: str) -> list[float]:
#     if not text:
#         return []
#     vectorizer = _get_rag_vectorizer()
#     embedding = vectorizer.transform([text]).toarray()[0]
#     return embedding.tolist()
#
#
# def _cosine_similarity(a: list[float], b: list[float]) -> float:
#     if not a or not b or len(a) != len(b):
#         return 0.0
#     return sum(x * y for x, y in zip(a, b))
#
#
# SUPPORTED_TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".csv", ".json", ".py", ".c", ".cpp", ".h"}
# SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}
#
#
# async def _get_reader():
#     """لودر اسینک و ایمن موتور OCR برای جلوگیری از تداخل ریکوئست‌ها"""
#     global _reader
#     if _reader is not None:
#         return _reader
#
#     async with _reader_lock:
#         if _reader is None:
#             import easyocr
#
#             gpu = bool(settings.OCR_GPU)
#             if gpu:
#                 try:
#                     import torch
#                     if not torch.cuda.is_available():
#                         logger.warning("easyocr GPU requested but torch.cuda is not available; falling back to CPU")
#                         gpu = False
#                 except Exception as exc:
#                     logger.warning("easyocr GPU requested but failed to import torch; falling back to CPU: %s", exc)
#                     gpu = False
#
#             # مقداردهی نهایی مدل به صورت ترد-ایمن
#             _reader = easyocr.Reader([settings.OCR_LANG or "fa", "en"], gpu=gpu)
#             logger.info("easyocr Reader initialized successfully with %s", "GPU" if gpu else "CPU")
#     return _reader
#
# #
# # async def ocr_base64_image(base64_data: str) -> str:
# #     """OCR یک تصویر به صورت کاملاً Async بدون بلاک کردن Event Loop پایتون"""
# #     try:
# #         if "," in base64_data:
# #             base64_data = base64_data.split(",", 1)[1]
# #         image_bytes = base64.b64decode(base64_data)
# #         suffix = ".png"
# #
# #         with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
# #             tmp.write(image_bytes)
# #             tmp_path = tmp.name
# #
# #         reader = await _get_reader()
# #         loop = asyncio.get_running_loop()
# #
# #         # اجرای پردازش سنگین تصویر در ThreadPool مجزا
# #         results = await loop.run_in_executor(None, reader.readtext, tmp_path)
# #
# #         lines = [text for (_, text, conf) in results if conf > 0.3]
# #         text = "\n".join(lines)
# #
# #         os.unlink(tmp_path)
# #         return text.strip()
# #     except Exception as exc:
# #         logger.warning("OCR process failed: %s", exc)
# #         return ""
#
#
# # ۱. تعریف یک دیکشنری در سطح ماژول برای ذخیره نتایج OCR
# # _ocr_cache: dict[str, str] = {}
# #
# # async def ocr_base64_image(base64_data: str) -> str:
# #     """OCR یک تصویر به صورت کاملاً Async همراه با سیستم کش برای جلوگیری از تکرار روی CPU"""
# #     try:
# #         if "," in base64_data:
# #             base64_data = base64_data.split(",", 1)[1]
# #
# #         # ۲. محاسبه هش MD5 از دیتای تصویر برای استفاده به عنوان کلید کش
# #         img_hash = hashlib.md5(base64_data.encode('utf-8')).hexdigest()
# #
# #         # ۳. بررسی وجود نتیجه در کش
# #         if img_hash in _ocr_cache:
# #             logger.info("🎯 OCR Cache Hit! Reusing text for image hash: %s", img_hash)
# #             return _ocr_cache[img_hash]
# #
# #         # اگر در کش نبود، پردازش سنگین آغاز می‌شود
# #         image_bytes = base64.b64decode(base64_data)
# #         suffix = ".png"
# #
# #         with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
# #             tmp.write(image_bytes)
# #             tmp_path = tmp.name
# #
# #         reader = await _get_reader()
# #         loop = asyncio.get_running_loop()
# #
# #         # اجرای پردازش سنگین تصویر در ThreadPool
# #         results = await loop.run_in_executor(None, reader.readtext, tmp_path)
# #
# #         lines = [text for (_, text, conf) in results if conf > 0.3]
# #         text = "\n".join(lines).strip()
# #
# #         os.unlink(tmp_path)
# #
# #         # ۴. ذخیره نتیجه در کش برای ریکوئست‌ها و لوپ‌های بعدی
# #         if text:
# #             _ocr_cache[img_hash] = text
# #
# #         return text
# #     except Exception as exc:
# #         logger.warning("OCR process failed: %s", exc)
# #         return ""
#
# # بخشی از فایل app/services/rag_service.py در پروژه اصلی چت (Port 8000)
#
# # کِش درون‌حافظه‌ای در سطح سرور اصلی برای نجات کانتکست‌ها و تاریخچه چت
# _ocr_cache: dict[str, str] = {}
#
#
# async def ocr_base64_image(base64_data: str) -> str:
#     """
#     استخراج متن با متد کش هوشمند.
#     اگر عکس جدید باشد، آن را به میکروسرویس پورت 8010 می‌فرستد.
#     """
#     if not base64_data:
#         return ""
#
#     try:
#         # ۱. محاسبه هش تصویر برای بررسی وضعیت کِش
#         image_hash = hashlib.md5(base64_data.encode("utf-8")).hexdigest()
#
#         # ۲. بررسی سریع کش برای جلوگیری از ارسال پیام‌های قدیمی تاریخچه چت
#         if image_hash in _ocr_cache:
#             logger.info("🎯 OCR Cache Hit! Reusing extracted text for hash: %s", image_hash)
#             return _ocr_cache[image_hash]
#
#         # ۳. ارسال به میکروسرویس مجزا در صورت عدم وجود در کش
#         logger.info("🚀 Cache Miss. Sending image to isolated OCR microservice...")
#
#         async with httpx.AsyncClient(timeout=45.0) as client:
#             payload = {"image_base64": base64_data}
#             response = await client.post(settings.OCR_SERVICE_URL, json=payload)
#
#             if response.status_code == 200:
#                 extracted_text = response.json().get("text", "")
#
#                 # ذخیره در کش اصلی (حتی اگر متن خالی بود، کش می‌شود تا دوباره پردازش نشود)
#                 _ocr_cache[image_hash] = extracted_text
#                 logger.info("✅ OCR processing completed via microservice and cached.")
#                 return extracted_text
#             else:
#                 logger.error("❌ OCR microservice returned error status %d: %s", response.status_code, response.text)
#                 return ""
#
#     except httpx.RequestError as exc:
#         logger.error("❌ Network error while connecting to OCR Microservice: %s", exc)
#         return ""
#     except Exception as e:
#         logger.error("❌ Unexpected error in ocr_base64_image client: %s", e)
#         return ""
#
#
#
# def _safe_filename(filename: str) -> str:
#     name = Path(filename or "upload.bin").name
#     return re.sub(r"[^A-Za-z0-9._-]+", "_", name)
#
#
# def _chunk_text(text: str) -> list[str]:
#     size = max(settings.RAG_CHUNK_SIZE, 200)
#     overlap = min(max(settings.RAG_CHUNK_OVERLAP, 0), size // 2)
#     cleaned = re.sub(r"\n{3,}", "\n\n", text).strip()
#     if not cleaned:
#         return []
#
#     chunks: list[str] = []
#     start = 0
#     while start < len(cleaned):
#         end = min(start + size, len(cleaned))
#         chunks.append(cleaned[start:end].strip())
#         if end == len(cleaned):
#             break
#         start = max(end - overlap, start + 1)
#     return [chunk for chunk in chunks if chunk]
#
#
# def _extract_pdf_text(path: Path) -> str:
#     try:
#         from pypdf import PdfReader
#     except ImportError as exc:
#         raise HTTPException(
#             status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
#             detail="PDF parsing requires pypdf. Install requirements before uploading PDFs.",
#         ) from exc
#
#     reader = PdfReader(str(path))
#     return "\n\n".join(page.extract_text() or "" for page in reader.pages)
#
#
# async def _extract_image_text_async(path: Path) -> str:
#     """استخراج متن تصویر برای فایل‌های آپلودی به صورت غیربلاک‌کننده"""
#     reader = await _get_reader()
#     loop = asyncio.get_running_loop()
#     results = await loop.run_in_executor(None, reader.readtext, str(path))
#     lines = [text for (_, text, conf) in results if conf > 0.3]
#     return "\n".join(lines)
#
#
# async def extract_text_async(path: Path, content_type: str = "") -> str:
#     suffix = path.suffix.lower()
#     if suffix == ".pdf" or content_type == "application/pdf":
#         return _extract_pdf_text(path)
#
#     if suffix in SUPPORTED_IMAGE_SUFFIXES or content_type.startswith("image/"):
#         return await _extract_image_text_async(path)
#
#     if suffix in SUPPORTED_TEXT_SUFFIXES or content_type.startswith("text/"):
#         return path.read_text(encoding="utf-8", errors="ignore")
#
#     raise HTTPException(
#         status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
#         detail=f"Unsupported file type: {suffix or content_type or 'unknown'}",
#     )
#
#
# async def create_rag_file(
#         db: AsyncSession,
#         user_id: int,
#         upload: UploadFile,
#         process: bool = True,
# ) -> RAGFile:
#     upload_dir = Path(settings.RAG_UPLOAD_DIR)
#     upload_dir.mkdir(parents=True, exist_ok=True)
#
#     file_id = uuid.uuid4()
#     filename = _safe_filename(upload.filename or "upload.bin")
#     path = upload_dir / f"{file_id}_{filename}"
#
#     with path.open("wb") as out:
#         shutil.copyfileobj(upload.file, out)
#
#     rag_file = RAGFile(
#         id=file_id,
#         user_id=user_id,
#         filename=filename,
#         content_type=upload.content_type or "",
#         path=str(path),
#         status="uploaded",
#     )
#     db.add(rag_file)
#     await db.flush()
#
#     if process:
#         await ingest_rag_file(db, rag_file)
#
#     return rag_file
#
#
# async def ingest_rag_file(db: AsyncSession, rag_file: RAGFile) -> RAGFile:
#     try:
#         text = await extract_text_async(Path(rag_file.path), rag_file.content_type or "")
#         chunks = _chunk_text(text)
#         if not chunks:
#             raise ValueError("No extractable text found in file")
#
#         await db.execute(delete(RAGChunk).where(RAGChunk.file_id == rag_file.id))
#
#         embedding_list = [_embed_text(chunk) for chunk in chunks]
#         for index, (chunk, embedding) in enumerate(zip(chunks, embedding_list)):
#             db.add(
#                 RAGChunk(
#                     file_id=rag_file.id,
#                     chunk_index=index,
#                     content=chunk,
#                     token_count=max(1, len(chunk.split())),
#                     metadata_={"embedding": embedding},
#                 )
#             )
#
#         rag_file.status = "ready"
#         rag_file.error = ""
#         rag_file.processed_at = datetime.now(timezone.utc)
#         await db.flush()
#         return rag_file
#     except Exception as exc:
#         rag_file.status = "failed"
#         rag_file.error = str(exc)
#         await db.flush()
#         raise
#
#
# async def list_rag_files(db: AsyncSession, user_id: int) -> list[dict]:
#     result = await db.execute(
#         select(RAGFile, func.count(RAGChunk.id).label("chunk_count"))
#         .outerjoin(RAGChunk, RAGChunk.file_id == RAGFile.id)
#         .where(RAGFile.user_id == user_id)
#         .group_by(RAGFile.id)
#         .order_by(RAGFile.created_at.desc())
#     )
#     return [
#         {
#             "id": rag_file.id,
#             "filename": rag_file.filename,
#             "content_type": rag_file.content_type,
#             "status": rag_file.status,
#             "created_at": rag_file.created_at,
#             "chunk_count": chunk_count,
#         }
#         for rag_file, chunk_count in result.all()
#     ]
#
#
# def _score(query_terms: set[str], content: str) -> tuple[float, int]:
#     if not query_terms:
#         return 0.0, 0
#     content_terms = {term.lower() for term in re.findall(r"\w+", content or "") if len(term) > 2}
#     match_count = sum(1 for term in query_terms if term in content_terms)
#     score = match_count / len(query_terms) if query_terms else 0.0
#     return score, match_count
#
#
# async def retrieve_context(
#         db: AsyncSession,
#         user_id: int,
#         file_ids: list[uuid.UUID],
#         query: str,
# ) -> str:
#     # گیت خروج زودهنگام شماره یک: فایل ای‌دی اصلاً ارسال نشده
#     if not file_ids:
#         return ""
#
#     query_terms = {term.lower() for term in re.findall(r"\w+", query or "") if len(term) > 2}
#     if not query_terms:
#         logger.info("Empty or too short query for RAG retrieval; skipping context injection")
#         return ""
#
#     result = await db.execute(
#         select(RAGChunk, RAGFile.filename)
#         .join(RAGFile, RAGFile.id == RAGChunk.file_id)
#         .where(
#             RAGFile.user_id == user_id,
#             RAGFile.status == "ready",
#             RAGFile.id.in_(file_ids),
#         )
#     )
#     rows = result.all()
#     if not rows:
#         return ""
#
#     chunk_embeddings = []
#     for chunk, filename in rows:
#         embedding = None
#         if chunk.metadata_ and isinstance(chunk.metadata_, dict):
#             embedding = chunk.metadata_.get("embedding")
#         if isinstance(embedding, list) and len(embedding) == settings.RAG_EMBEDDING_DIM:
#             chunk_embeddings.append((chunk, filename, embedding))
#
#     ranked = []
#     if chunk_embeddings:
#         query_embedding = _embed_text(query)
#         if not query_embedding or sum(abs(x) for x in query_embedding) == 0:
#             logger.info("Query embedding is empty; skipping semantic RAG retrieval")
#             return ""
#         ranked = sorted(
#             (
#                 (
#                     chunk,
#                     filename,
#                     max(
#                         _cosine_similarity(query_embedding, embedding),
#                         _score(query_terms, chunk.content)[0],
#                     ),
#                 )
#                 for chunk, filename, embedding in chunk_embeddings
#             ),
#             key=lambda item: item[2],
#             reverse=True,
#         )
#         logger.info("Using semantic+lexical retrieval for RAG context; candidate chunks=%d", len(ranked))
#     else:
#         ranked = sorted(
#             ((chunk, filename, *_score(query_terms, chunk.content)[0]) for chunk, filename in rows),
#             key=lambda item: item[2],
#             reverse=True,
#         )
#         logger.info("No semantic embeddings available; falling back to lexical retrieval")
#
#     min_score = settings.RAG_MIN_SCORE
#     if len(query_terms) <= 3:
#         min_score = max(min_score, 0.5)
#
#     selected = [item for item in ranked if item[2] >= min_score][: settings.RAG_TOP_K]
#     if not selected:
#         logger.info(
#             "No RAG chunk passed min_score=%.2f for query with %d terms; skipping context injection",
#             min_score,
#             len(query_terms),
#         )
#         return ""
#
#     max_context_tokens = settings.RAG_MAX_CONTEXT_TOKENS
#     tokens = 0
#     blocks = []
#     for chunk, filename, score in selected:
#         chunk_tokens = estimate_text_tokens(chunk.content)
#         if tokens + chunk_tokens > max_context_tokens:
#             logger.info(
#                 "RAG context token limit reached: %d/%d tokens; stopping selection",
#                 tokens,
#                 max_context_tokens,
#             )
#             break
#         blocks.append(f"[source: {filename}#{chunk.chunk_index}]\n{chunk.content}")
#         tokens += chunk_tokens
#
#     if not blocks:
#         logger.info(
#             "Relevant RAG chunks exist but none fit within %d token budget; skipping context injection",
#             max_context_tokens,
#         )
#         return ""
#
#     logger.info(
#         "Selected %d RAG chunks with min_score=%.2f and total_context_tokens=%d",
#         len(blocks),
#         min_score,
#         tokens,
#     )
#     return "\n\n".join(blocks)


from __future__ import annotations

import base64
import logging
import os
import re
import shutil
import tempfile
import uuid
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict
import hashlib
import httpx

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.llm import RAGChunk, RAGFile
from app.services.embedding_service import embed_text, embed_texts
from app.services.token_utils import estimate_text_tokens

settings = get_settings()
logger = logging.getLogger(__name__)

# آرایه‌ها و متغیرهای سراسری سیستم
_reader = None
_reader_lock = asyncio.Lock()
_ocr_cache: dict[str, str] = {}

SUPPORTED_TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".csv", ".json", ".py", ".c", ".cpp", ".h"}
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}


# ─── EMBEDDINGS ───────────────────────────────────────────────────────────────

def _embed_text(text: str) -> list[float]:
    return embed_text(text)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


# ─── OCR ENGINE & BASE64 PARSER ────────────────────────────────────────────────

async def _get_reader():
    global _reader
    if _reader is not None:
        return _reader

    async with _reader_lock:
        if _reader is None:
            import easyocr
            gpu = bool(settings.OCR_GPU)
            if gpu:
                try:
                    import torch
                    if not torch.cuda.is_available():
                        gpu = False
                except Exception:
                    gpu = False

            _reader = easyocr.Reader([settings.OCR_LANG or "fa", "en"], gpu=gpu)
            logger.info("easyocr Reader initialized successfully on %s", "GPU" if gpu else "CPU")
    return _reader


async def ocr_base64_image(base64_data: str) -> str:
    """استخراج متن تصویر از میکروسرویس ایزوله همراه با مکانیزم کش هوشمند"""
    if not base64_data:
        return ""

    try:
        if "," in base64_data:
            base64_data = base64_data.split(",", 1)[1]

        image_hash = hashlib.md5(base64_data.encode("utf-8")).hexdigest()

        if image_hash in _ocr_cache:
            logger.info("🎯 OCR Cache Hit! Reusing extracted text for hash: %s", image_hash)
            return _ocr_cache[image_hash]

        logger.info("🚀 Cache Miss. Sending image to isolated OCR microservice...")
        async with httpx.AsyncClient(timeout=45.0) as client:
            payload = {"image_base64": base64_data}
            response = await client.post(settings.OCR_SERVICE_URL, json=payload)

            if response.status_code == 200:
                extracted_text = response.json().get("text", "").strip()
                _ocr_cache[image_hash] = extracted_text
                logger.info("✅ OCR processing completed via microservice and cached.")
                return extracted_text

            logger.error("❌ OCR microservice returned error status %d", response.status_code)
            return ""

    except Exception as e:
        logger.error("❌ Unexpected error in ocr_base64_image client: %s", e)
        return ""


# ─── FILE PARSERS & TEXT EXTRACTIONS ──────────────────────────────────────────

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
    return [c for c in chunks if c]


def _extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="PDF parsing requires pypdf.",
        ) from exc

    reader = PdfReader(str(path))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


async def _extract_image_text_async(path: Path) -> str:
    reader = await _get_reader()
    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(None, reader.readtext, str(path))
    return "\n".join([text for (_, text, conf) in results if conf > 0.3])


async def extract_text_async(path: Path, content_type: str = "") -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf" or content_type == "application/pdf":
        return _extract_pdf_text(path)
    if suffix in SUPPORTED_IMAGE_SUFFIXES or content_type.startswith("image/"):
        return await _extract_image_text_async(path)
    if suffix in SUPPORTED_TEXT_SUFFIXES or content_type.startswith("text/"):
        return path.read_text(encoding="utf-8", errors="ignore")

    raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=f"Unsupported file: {suffix}")


# ─── INGESTION PIPELINE ───────────────────────────────────────────────────────

def _validate_upload_type(filename: str, content_type: str) -> None:
    """فقط پسوندها/نوع‌های پشتیبانی‌شده اجازه‌ی آپلود دارند."""
    suffix = Path(filename or "").suffix.lower()
    allowed = SUPPORTED_TEXT_SUFFIXES | SUPPORTED_IMAGE_SUFFIXES | {".pdf"}
    ctype = (content_type or "").lower()
    ctype_ok = (
        ctype == "application/pdf"
        or ctype.startswith("image/")
        or ctype.startswith("text/")
    )
    if suffix not in allowed and not ctype_ok:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {suffix or content_type or 'unknown'}",
        )


async def create_rag_file(db: AsyncSession, user_id: int, upload: UploadFile, process: bool = True) -> RAGFile:
    upload_dir = Path(settings.RAG_UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    _validate_upload_type(upload.filename or "", upload.content_type or "")

    file_id = uuid.uuid4()
    filename = _safe_filename(upload.filename or "upload.bin")
    path = upload_dir / f"{file_id}_{filename}"

    # کپی استریمی با اعمال سقف حجم تا از پر شدن دیسک / DoS جلوگیری شود
    max_bytes = max(1, settings.RAG_MAX_FILE_SIZE_MB) * 1024 * 1024
    written = 0
    try:
        with path.open("wb") as out:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    out.close()
                    path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds maximum allowed size of {settings.RAG_MAX_FILE_SIZE_MB} MB",
                    )
                out.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to store uploaded file: {exc}",
        )

    rag_file = RAGFile(
        id=file_id, user_id=user_id, filename=filename,
        content_type=upload.content_type or "", path=str(path), status="uploaded",
    )
    db.add(rag_file)
    await db.flush()

    if process:
        await ingest_rag_file(db, rag_file)
    return rag_file


async def ingest_rag_file(db: AsyncSession, rag_file: RAGFile) -> RAGFile:
    try:
        text = await extract_text_async(Path(rag_file.path), rag_file.content_type or "")
        chunks = _chunk_text(text)
        if not chunks:
            raise ValueError("No extractable text found in file")

        await db.execute(delete(RAGChunk).where(RAGChunk.file_id == rag_file.id))

        embeddings = embed_texts(chunks)
        for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            db.add(
                RAGChunk(
                    file_id=rag_file.id, chunk_index=index, content=chunk,
                    token_count=max(1, len(chunk.split())), metadata_={"embedding": embedding},
                )
            )

        rag_file.status, rag_file.error = "ready", ""
        rag_file.processed_at = datetime.now(timezone.utc)
        await db.flush()
        return rag_file
    except Exception as exc:
        rag_file.status, rag_file.error = "failed", str(exc)
        await db.flush()
        raise


async def reindex_rag_file(db: AsyncSession, rag_file: RAGFile) -> RAGFile:
    """بازسازی embedding چانک‌های موجود با مدل فعلی (بدون re-extract فایل)."""
    result = await db.execute(
        select(RAGChunk)
        .where(RAGChunk.file_id == rag_file.id)
        .order_by(RAGChunk.chunk_index)
    )
    chunks = list(result.scalars().all())
    if not chunks:
        return await ingest_rag_file(db, rag_file)

    embeddings = embed_texts([c.content for c in chunks])
    if len(embeddings) != len(chunks):
        raise ValueError("Embedding batch size mismatch")

    for chunk, embedding in zip(chunks, embeddings):
        meta = dict(chunk.metadata_ or {}) if isinstance(chunk.metadata_, dict) else {}
        meta["embedding"] = embedding
        chunk.metadata_ = meta

    rag_file.status, rag_file.error = "ready", ""
    rag_file.processed_at = datetime.now(timezone.utc)
    await db.flush()
    return rag_file


async def get_rag_file_for_user(
    db: AsyncSession, user_id: int, file_id: uuid.UUID
) -> RAGFile | None:
    result = await db.execute(
        select(RAGFile).where(RAGFile.id == file_id, RAGFile.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def list_rag_files(db: AsyncSession, user_id: int) -> list[dict]:
    result = await db.execute(
        select(RAGFile, func.count(RAGChunk.id).label("chunk_count"))
        .outerjoin(RAGChunk, RAGChunk.file_id == RAGFile.id)
        .where(RAGFile.user_id == user_id).group_by(RAGFile.id).order_by(RAGFile.created_at.desc())
    )
    return [
        {
            "id": f.id, "filename": f.filename, "content_type": f.content_type,
            "status": f.status, "created_at": f.created_at, "chunk_count": cc,
        }
        for f, cc in result.all()
    ]


def _score(query_terms: set[str], content: str) -> tuple[float, int]:
    if not query_terms:
        return 0.0, 0
    content_terms = {term.lower() for term in re.findall(r"\w+", content or "") if len(term) > 2}
    match_count = sum(1 for term in query_terms if term in content_terms)
    return (match_count / len(query_terms) if query_terms else 0.0), match_count


# ─── CONTEXT RETRIEVAL (FAIR-SHARE ROUND-ROBIN) ───────────────────────────────

async def retrieve_context(db: AsyncSession, user_id: int, file_ids: list[uuid.UUID], query: str) -> str:
    if not file_ids:
        return ""

    query_terms = {t.lower() for t in re.findall(r"\w+", query or "") if len(t) > 2}
    if not query_terms:
        logger.info("Empty or short query for RAG; skipping context injection.")
        return ""

    result = await db.execute(
        select(RAGChunk, RAGFile.filename).join(RAGFile, RAGFile.id == RAGChunk.file_id)
        .where(RAGFile.user_id == user_id, RAGFile.status == "ready", RAGFile.id.in_(file_ids))
    )
    rows = result.all()
    if not rows:
        return ""

    # کاندید کردن و امتیاز دهی چانک‌ها
    ranked = []
    query_embedding = _embed_text(query)
    has_semantic = query_embedding and sum(abs(x) for x in query_embedding) > 0

    for chunk, filename in rows:
        embedding = chunk.metadata_.get("embedding") if (
                    chunk.metadata_ and isinstance(chunk.metadata_, dict)) else None
        lex_score, _ = _score(query_terms, chunk.content)

        if has_semantic and isinstance(embedding, list) and len(embedding) == settings.RAG_EMBEDDING_DIM:
            score = max(_cosine_similarity(query_embedding, embedding), lex_score)
        else:
            score = lex_score

        ranked.append((chunk, filename, score))

    ranked = sorted(ranked, key=lambda item: item[2], reverse=True)

    min_score = settings.RAG_MIN_SCORE
    if len(query_terms) <= 3:
        min_score = max(min_score, 0.5)

    # فیلتر بر اساس حداقل امتیاز
    valid_chunks = [item for item in ranked if item[2] >= min_score]
    if not valid_chunks:
        logger.info("No RAG chunk passed min_score=%.2f", min_score)
        return ""

    # 🌟 تسهیم عادلانه چانک‌ها به تفکیک نام فایل (تکنیک Round-Robin برای جلوگیری از File Starvation)
    chunks_by_file = defaultdict(list)
    for item in valid_chunks:
        _, filename, _ = item
        chunks_by_file[filename].append(item)

    selected = []
    tokens = 0
    max_context_tokens = settings.RAG_MAX_CONTEXT_TOKENS

    has_more = True
    while has_more and tokens < max_context_tokens:
        has_more = False
        for filename in list(chunks_by_file.keys()):
            if chunks_by_file[filename]:
                has_more = True
                item = chunks_by_file[filename].pop(0)  # برابری شانس فایل‌ها برای ارسال چانک برترشان
                chunk, _, _ = item

                chunk_tokens = estimate_text_tokens(chunk.content)
                if tokens + chunk_tokens <= max_context_tokens:
                    selected.append(item)
                    tokens += chunk_tokens
                else:
                    has_more = False
                    break

    blocks = [f"\n{c.content}" for c, fname, _ in selected]
    logger.info("Selected %d RAG chunks across files. Total tokens: %d/%d", len(blocks), tokens, max_context_tokens)
    return "\n\n".join(blocks)