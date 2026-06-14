import asyncio
from unittest.mock import AsyncMock, patch

from app.schemas.schemas import ChatCompletionRequest, ChatMessage
from app.services.openwebui_files import (
    extract_openwebui_file_refs,
    sanitize_raw_for_validation,
    enrich_request_from_openwebui,
    _wrap_with_file_context,
    extract_file_refs_from_chat,
    filter_new_chat_file_refs,
)


OWUI_RAW = {
    "model": "qwen3-coder-30b-a3b-instruct",
    "messages": [{"role": "user", "content": "خلاصه PDF را بگو"}],
    "files": [
        {
            "type": "file",
            "id": "26f65b14-aaaa-bbbb-cccc-ddddeeeeffff",
            "name": "article.pdf",
            "file": {
                "id": "26f65b14-aaaa-bbbb-cccc-ddddeeeeffff",
                "name": "article.pdf",
            },
        }
    ],
    "stream": True,
}


def test_extract_refs_from_nested_owui_files():
    refs = extract_openwebui_file_refs(OWUI_RAW)
    assert refs == [("26f65b14-aaaa-bbbb-cccc-ddddeeeeffff", "article.pdf")]


def test_extract_refs_from_metadata_files():
    raw = {
        "messages": [{"role": "user", "content": "hi"}],
        "metadata": {"files": [{"id": "abc-123", "name": "doc.txt"}]},
    }
    refs = extract_openwebui_file_refs(raw)
    assert refs == [("abc-123", "doc.txt")]


def test_sanitize_strips_owui_files_from_body():
    clean = sanitize_raw_for_validation(OWUI_RAW)
    assert clean["files"] == []


def test_sanitize_keeps_gateway_rag_files():
    raw = {
        "files": [{"id": "550e8400-e29b-41d4-a716-446655440000", "name": "rag.pdf"}],
        "messages": [],
    }
    clean = sanitize_raw_for_validation(raw)
    assert len(clean["files"]) == 1
    assert clean["files"][0]["id"] == "550e8400-e29b-41d4-a716-446655440000"


def test_wrap_with_file_context():
    out = _wrap_with_file_context("سؤال", [("a.pdf", "TEXT")])
    assert "<source id=\"1\" name=\"a.pdf\">TEXT</source>" in out
    assert "<user_query>\nسؤال\n</user_query>" in out


def test_extract_file_refs_from_chat_history():
    chat = {
        "chat": {
            "history": {
                "messages": {
                    "u1": {"role": "user", "content": "hi", "timestamp": 1, "files": []},
                    "u2": {
                        "role": "user",
                        "content": "pdf?",
                        "timestamp": 2,
                        "files": [{"type": "file", "id": "fid-1", "name": "a.pdf"}],
                    },
                }
            }
        }
    }
    refs = extract_file_refs_from_chat(chat)
    assert refs == [("fid-1", "a.pdf")]


def test_filter_new_chat_file_refs():
    from app.core.attachment_cache import set_seen_attachments, delete_seen_attachments

    delete_seen_attachments("id:chat-1")
    refs = [("fid-1", "a.pdf"), ("fid-2", "b.pdf")]
    assert len(filter_new_chat_file_refs("chat-1", refs)) == 2
    set_seen_attachments("id:chat-1", {"a.pdf"})
    new = filter_new_chat_file_refs("chat-1", refs)
    assert new == [("fid-2", "b.pdf")]
    delete_seen_attachments("id:chat-1")


def test_enrich_injects_fetched_content():
    body = ChatCompletionRequest.model_validate(sanitize_raw_for_validation(OWUI_RAW))
    with patch(
        "app.services.openwebui_files.fetch_openwebui_file_text",
        new=AsyncMock(return_value="PDF BODY HERE"),
    ):
        enriched = asyncio.run(enrich_request_from_openwebui(OWUI_RAW, body, chat_id=None))

    last = enriched.messages[-1]
    assert "PDF BODY HERE" in str(last.content)
    assert "article.pdf" in str(last.content)
    assert enriched.files == []


def test_enrich_skips_when_already_has_sources():
    body = ChatCompletionRequest(
        model="m",
        messages=[
            ChatMessage(
                role="user",
                content=_wrap_with_file_context("q", [("x.pdf", "A" * 4000)]),
            )
        ],
    )
    with patch(
        "app.services.openwebui_files.fetch_openwebui_file_text",
        new=AsyncMock(return_value="SHOULD NOT FETCH"),
    ) as mock_fetch:
        enriched = asyncio.run(enrich_request_from_openwebui(OWUI_RAW, body, chat_id=None))
    mock_fetch.assert_not_called()
    assert enriched.messages[-1].content == body.messages[-1].content
