import asyncio

from app.services import chat_completion_service as ccs


def test_last_user_index():
    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "second"},
    ]
    assert ccs._last_user_index(messages) == 3


def test_last_user_index_none():
    assert ccs._last_user_index([{"role": "system", "content": "s"}]) == -1


def test_truncate_long_text_preserves_tail():
    # دنباله‌ی متمایز در انتها (شبیه سؤال واقعی کاربر) باید پس از برش میانی حفظ شود
    long = ("filler " * 4000) + "QUESTION_AT_END"
    out = ccs._truncate_text_to_tokens(long, 50)
    assert len(out) < len(long)
    assert "QUESTION_AT_END" in out
    from app.services.token_utils import estimate_text_tokens
    assert estimate_text_tokens(out) <= 50


def test_truncate_keeps_short_text():
    assert ccs._truncate_text_to_tokens("hello", 100) == "hello"
    assert ccs._truncate_text_to_tokens("", 100) == ""


def test_flatten_skips_images_when_ocr_disabled():
    msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": "hello"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        ],
    }
    out = asyncio.run(ccs._flatten_content_async(msg, include_ocr=False))
    assert out == "hello"


def test_flatten_plain_string():
    msg = {"role": "user", "content": "just text"}
    out = asyncio.run(ccs._flatten_content_async(msg, include_ocr=True))
    assert out == "just text"


def test_to_openai_messages_disables_ocr():
    messages = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}]
    out = asyncio.run(ccs._to_openai_messages_async(messages, ocr_enabled=False))
    assert out == messages


def test_ocr_fallback_uses_last_images_when_new_not_detected(monkeypatch):
    msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": "متن عکس را بخوان"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        ],
    }

    async def fake_ocr(_url: str) -> str:
        return "OCR TEXT"

    monkeypatch.setattr(ccs, "current_turn_images", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(ccs, "_ocr_image_url", fake_ocr)

    out = asyncio.run(
        ccs._to_openai_messages_async(
            [msg],
            scope_files_per_turn=True,
            request_files=[],
            conversation_id=None,
        )
    )
    assert "OCR TEXT" in out[0]["content"]


def test_mixed_pdf_and_two_inline_images_ocr_both(monkeypatch):
    """سناریوی کاربر: PDF قدیمی + ۲ عکس inline جدید + تاریخچه — هر دو عکس OCR شوند."""
    from app.services import openwebui_content as owc
    from app.core.attachment_cache import reset_memory_fallback

    reset_memory_fallback()
    img_a = "data:image/png;base64," + ("A" * 120)
    img_b = "data:image/png;base64," + ("B" * 120)
    pdf = '<source id="1" name="old.pdf">' + ("PDF " * 2000) + "</source>"

    # نوبت قبلی فقط PDF
    turn1 = [{"role": "user", "content": f"<context>{pdf}</context>"}]
    owc.reset_conversation_sources(messages=turn1)
    owc.remember_conversation_sources(None, turn1)

    last_blob = (
        f"<context>{pdf}"
        f'<source id="2" name="scan-a">{img_a}</source>'
        f'<source id="3" name="scan-b">{img_b}</source></context>'
        "<user_query>این دو عکس را با مقاله بررسی کن</user_query>"
    )
    messages = [
        {"role": "user", "content": f"<context>{pdf}</context>"},
        {"role": "assistant", "content": "خلاصه مقاله"},
        {"role": "user", "content": "یک سؤال میانی"},
        {"role": "assistant", "content": "پاسخ"},
        {"role": "user", "content": last_blob},
    ]

    calls = []

    async def fake_ocr(url: str) -> str:
        calls.append(url)
        return f"OCR[{url[-3:]}]"

    monkeypatch.setattr(ccs, "_ocr_image_url", fake_ocr)

    out = asyncio.run(
        ccs._to_openai_messages_async(
            messages,
            scope_files_per_turn=True,
            request_files=[],
            conversation_id=None,
        )
    )
    last_content = out[-1]["content"]
    assert len(calls) == 2  # هر دو عکس OCR شدند
    assert "OCR[" in last_content


def test_trim_keeps_system_and_truncates_huge_last_message():
    huge = "token " * 5000
    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "old message"},
        {"role": "user", "content": huge},
    ]
    trimmed = ccs._trim_messages_to_budget(messages, max_prompt_tokens=300)
    # system message always retained
    assert trimmed[0]["role"] == "system"
    # last (huge) message retained but truncated
    assert trimmed[-1]["role"] == "user"
    assert len(trimmed[-1]["content"]) < len(huge)
