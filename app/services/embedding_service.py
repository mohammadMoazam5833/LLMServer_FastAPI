"""
Embedding معنایی برای RAG — جایگزین HashingVectorizer.

مدل پیش‌فرض: paraphrase-multilingual-MiniLM-L12-v2 (فارسی + انگلیسی، 384-dim)
برای bge-m3 در .env تنظیم کنید: RAG_EMBEDDING_MODEL=BAAI/bge-m3 و RAG_EMBEDDING_DIM=1024
"""
from __future__ import annotations

import logging
import threading

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

_model = None
_lock = threading.Lock()


def _get_model():
    global _model
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        from sentence_transformers import SentenceTransformer

        logger.info(
            "Loading embedding model %s on %s …",
            settings.RAG_EMBEDDING_MODEL,
            settings.RAG_EMBEDDING_DEVICE,
        )
        _model = SentenceTransformer(
            settings.RAG_EMBEDDING_MODEL,
            device=settings.RAG_EMBEDDING_DEVICE,
        )
        logger.info("Embedding model loaded.")
        return _model


def _to_float_list(vector) -> list[float]:
    if hasattr(vector, "tolist"):
        return vector.tolist()
    return [float(x) for x in vector]


def embed_text(text: str) -> list[float]:
    """یک بردار embedding برای متن (normalize شده برای cosine similarity)."""
    if not text or not text.strip():
        return []
    model = _get_model()
    vector = model.encode(text.strip(), normalize_embeddings=True)
    return _to_float_list(vector)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """batch embedding برای ingest."""
    cleaned = [t.strip() for t in texts if t and t.strip()]
    if not cleaned:
        return []
    model = _get_model()
    vectors = model.encode(cleaned, normalize_embeddings=True)
    return [_to_float_list(v) for v in vectors]
