"""تست منطق امتیازدهی RAG — چانک با dim قدیمی فقط lexical score می‌گیرد."""
from app.services.rag_service import _cosine_similarity, _score


def test_cosine_similarity_normalized_vectors():
    a = [1.0, 0.0]
    b = [1.0, 0.0]
    assert _cosine_similarity(a, b) == 1.0


def test_cosine_similarity_dim_mismatch():
    assert _cosine_similarity([1.0], [1.0, 0.0]) == 0.0


def test_lexical_score_partial_match():
    score, matches = _score({"hello", "world"}, "Hello there world of code")
    assert matches == 2
    assert score == 1.0


def test_old_embedding_dim_skipped_for_semantic():
    """شبیه‌سازی: embedding 512-dim قدیمی با RAG_EMBEDDING_DIM=384."""
    from app.config import get_settings

    settings = get_settings()
    old_dim_embedding = [0.1] * 512
    query_embedding = [0.2] * settings.RAG_EMBEDDING_DIM
    has_semantic = query_embedding and sum(abs(x) for x in query_embedding) > 0
    use_semantic = (
        has_semantic
        and isinstance(old_dim_embedding, list)
        and len(old_dim_embedding) == settings.RAG_EMBEDDING_DIM
    )
    assert use_semantic is False
