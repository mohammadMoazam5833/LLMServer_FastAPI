from unittest.mock import MagicMock, patch


@patch("sentence_transformers.SentenceTransformer")
def test_embed_text_returns_normalized_vector(mock_st_cls):
    mock_model = MagicMock()
    mock_model.encode.return_value = [0.6, 0.8]
    mock_st_cls.return_value = mock_model

    from app.services import embedding_service

    embedding_service._model = None
    result = embedding_service.embed_text("سلام hello")

    assert result == [0.6, 0.8]
    mock_model.encode.assert_called_once_with("سلام hello", normalize_embeddings=True)


@patch("sentence_transformers.SentenceTransformer")
def test_embed_texts_batch(mock_st_cls):
    mock_model = MagicMock()
    mock_model.encode.return_value = [[1.0, 0.0], [0.0, 1.0]]
    mock_st_cls.return_value = mock_model

    from app.services import embedding_service

    embedding_service._model = None
    result = embedding_service.embed_texts(["a", "b"])

    assert result == [[1.0, 0.0], [0.0, 1.0]]
    mock_model.encode.assert_called_once_with(["a", "b"], normalize_embeddings=True)


def test_embed_text_empty():
    from app.services import embedding_service

    assert embedding_service.embed_text("") == []
    assert embedding_service.embed_text("   ") == []
