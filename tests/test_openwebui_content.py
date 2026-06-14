from app.services.openwebui_content import (
    extract_user_query,
    filter_sources,
    file_names_from_request,
    scope_message_content,
    all_source_names,
    carrier_matches_last_question,
    files_attached_this_turn,
    resolve_turn_file_scope,
    find_file_content_index,
    sources_delta_for_conversation,
    attachments_delta_for_conversation,
    remember_conversation_sources,
    reset_conversation_sources,
    current_turn_images,
    conversation_key,
)
from app.core.attachment_cache import reset_memory_fallback


class _Msg:
    def __init__(self, role, content):
        self.role = role
        self.content = content


OWUI_TEMPLATE = """### Task:
Respond using context.

<context>
<source id="1" name="file_a.txt">CONTENT A</source>
<source id="2" name="file_b.txt">CONTENT B</source>
<source id="3" name="file_c.txt">CONTENT C</source>
</context>

<user_query>
What is in all three files?
</user_query>
"""


def _carrier_with_sources(names_and_content: list[tuple[str, str, str]]) -> str:
    sources = "\n".join(
        f'<source id="{sid}" name="{name}">{body}</source>'
        for sid, name, body in names_and_content
    )
    return (
        "### Task:\nRespond using context.\n\n"
        f"<context>\n{sources}\n</context>\n\n"
        "<user_query>\nSummarize attached files\n</user_query>\n"
    )


def test_extract_user_query():
    q = extract_user_query(OWUI_TEMPLATE)
    assert "three files" in q


def test_filter_sources_keeps_only_allowed():
    out = filter_sources(OWUI_TEMPLATE, {"file_b.txt"})
    assert "CONTENT B" in out
    assert "CONTENT A" not in out
    assert "CONTENT C" not in out


def test_filter_sources_empty_allowed_strips_all_files():
    out = filter_sources(OWUI_TEMPLATE, set())
    assert "CONTENT A" not in out
    assert "CONTENT B" not in out
    assert "three files" in out


def test_historical_message_strips_files():
    scoped, _ = scope_message_content(
        OWUI_TEMPLATE,
        is_current_turn=False,
        allowed_names=set(),
    )
    assert "CONTENT A" not in scoped
    assert "three files" in scoped


def test_current_turn_with_files_keeps_only_attached():
    scoped, _ = scope_message_content(
        OWUI_TEMPLATE,
        is_current_turn=True,
        allowed_names={"file_a.txt", "file_c.txt"},
    )
    assert "CONTENT A" in scoped
    assert "CONTENT C" in scoped
    assert "CONTENT B" not in scoped


def test_current_turn_no_files_strips_old_sources():
    scoped, _ = scope_message_content(
        OWUI_TEMPLATE,
        is_current_turn=True,
        allowed_names=set(),
        keep_files=False,
    )
    assert "CONTENT A" not in scoped
    assert "CONTENT B" not in scoped
    assert "three files" in scoped


def test_current_turn_short_text_no_sources():
    scoped, _ = scope_message_content("فقط یک سؤال کوتاه", is_current_turn=True, allowed_names=set())
    assert scoped == "فقط یک سؤال کوتاه"


def test_carrier_matches_last_question():
    carrier = OWUI_TEMPLATE
    last = "What is in all three files?"
    assert carrier_matches_last_question(carrier, last)


def test_carrier_no_match_means_no_merge():
    carrier = OWUI_TEMPLATE
    last = "سؤال جدید بدون فایل"
    assert not carrier_matches_last_question(carrier, last)


def test_inline_file_kept_on_current_turn():
    big = "LINE\n" * 500 + "END"
    scoped, _ = scope_message_content(big, is_current_turn=True, allowed_names=set())
    assert "LINE" in scoped
    assert len(scoped) > 2000


def test_short_historical_text_preserved():
    scoped, _ = scope_message_content("سلام، این فایل را بخوان", is_current_turn=False, allowed_names=set())
    assert scoped == "سلام، این فایل را بخوان"


def test_file_names_from_request():
    class F:
        def __init__(self, id, name):
            self.id = id
            self.name = name

    names = file_names_from_request([F("uuid-1", "doc.pdf")])
    assert "doc.pdf" in names
    assert "uuid-1" in names


def test_all_source_names():
    names = all_source_names(OWUI_TEMPLATE)
    assert "file_a.txt" in names
    assert "1" in names


def test_files_attached_false_on_text_followup():
    messages = [
        _Msg("user", OWUI_TEMPLATE),
        _Msg("assistant", "پاسخ قبلی"),
        _Msg("user", "در مورد فایل های فرستاده شده صحبت کن"),
    ]
    assert not files_attached_this_turn([], messages)
    keep, allowed, reason = resolve_turn_file_scope([], messages)
    assert keep is False
    assert allowed == set()
    assert reason == "no-new-attach"


def test_carrier_merge_skips_stale_files_when_question_repeats():
    """PDF دوم: سؤال مشابه نباید فایل قدیمی حامل را دوباره attach کند."""
    reset_memory_fallback()

    query = "خلاصه این فایل را بگو"
    pdf1 = (
        "### Task:\nRespond using context.\n\n"
        '<context>\n<source id="1" name="article_one.pdf">ARTICLE ONE BODY</source>\n</context>\n\n'
        f"<user_query>\n{query}\n</user_query>\n"
    )
    turn1 = [_Msg("user", pdf1)]
    reset_conversation_sources(messages=turn1)
    remember_conversation_sources(None, turn1)

    # کاربر PDF دوم فرستاده ولی OWUI هنوز فقط سؤال کوتاه + حامل قدیمی را فوروارد کرده
    turn_stale = [
        _Msg("user", pdf1),
        _Msg("assistant", "خلاصه مقاله اول"),
        _Msg("user", query),
    ]
    keep, allowed, reason = resolve_turn_file_scope([], turn_stale)
    assert keep is False
    assert allowed == set()
    assert reason == "no-new-attach"


def test_carrier_merge_only_fresh_sources_when_carrier_gains_pdf():
    """حامل قدیمی + PDF جدید در همان پیام — فقط فایل تازه در allowed."""
    reset_memory_fallback()

    query = "خلاصه این فایل را بگو"
    pdf1_carrier = (
        "### Task:\nRespond using context.\n\n"
        '<context>\n<source id="1" name="first.pdf">FIRST</source>\n</context>\n\n'
        f"<user_query>\n{query}\n</user_query>\n"
    )
    turn1 = [_Msg("user", pdf1_carrier)]
    remember_conversation_sources(None, turn1)

    both = (
        "### Task:\nRespond using context.\n\n"
        '<context>\n'
        '<source id="1" name="first.pdf">FIRST</source>\n'
        '<source id="2" name="second.pdf">SECOND</source>\n'
        "</context>\n\n"
        f"<user_query>\n{query}\n</user_query>\n"
    )
    turn2 = [
        _Msg("user", both),
        _Msg("user", query),
    ]
    keep, allowed, reason = resolve_turn_file_scope([], turn2)
    assert keep is True
    assert reason.startswith("conv-delta:") or reason.startswith("carrier-merge:")
    assert "second.pdf" in allowed
    assert "first.pdf" not in allowed


def test_last_message_file_kept_despite_stale_cache_collision():
    """باگ کاربر: PDF در آخرین پیام، ولی کش از چت قبلی (تصادم anchor) آن را قدیمی می‌پندارد."""
    reset_memory_fallback()

    pdf_carrier = _carrier_with_sources([
        ("1", "ling-et-al-2023.pdf", "PDF BODY " * 2000),
    ])

    # شبیه‌سازی تصادم: کش با همان conv_key از چت قبلی، فایل را «دیده» است
    stale_chat = [
        _Msg("user", "سلام"),
        _Msg("assistant", "سلام"),
        _Msg("user", pdf_carrier),
    ]
    remember_conversation_sources(None, stale_chat)

    # چت «جدید» با همان anchor اول ولی PDF فقط در آخرین پیام
    new_chat = [
        _Msg("user", "سلام"),
        _Msg("assistant", "سلام"),
        _Msg("user", pdf_carrier),
    ]
    keep, allowed, reason = resolve_turn_file_scope([], new_chat)
    assert keep is True
    assert "ling-et-al-2023.pdf" in allowed
    assert reason == "last-msg-fresh-source"


def test_last_message_inline_pdf_without_source_kept_despite_cache_collision():
    """OpenWebUI گاهی PDF را بدون <source> در آخرین پیام می‌گذارد؛ این هم فایل نوبت جاری است."""
    reset_memory_fallback()

    inline_pdf = (
        "### Task:\nRespond using context.\n\n"
        "<context>\n"
        + ("PDF BODY WITHOUT SOURCE TAG " * 5000)
        + "\n</context>\n\n"
        "<user_query>\nخلاصه این مقاله رو بگو\n</user_query>\n"
    )
    stale_chat = [
        _Msg("user", "سلام"),
        _Msg("assistant", "سلام"),
        _Msg("user", inline_pdf),
    ]
    remember_conversation_sources(None, stale_chat)

    new_chat = [
        _Msg("user", "سلام"),
        _Msg("assistant", "سلام"),
        _Msg("user", inline_pdf),
    ]
    keep, allowed, reason = resolve_turn_file_scope([], new_chat)
    assert keep is True
    assert allowed == set()
    assert reason == "last-msg-inline-file"


def test_last_message_fresh_source_ignores_history_files():
    """فایل قدیمی در history + فایل جدید در آخرین پیام — فقط فایل جدید."""
    reset_memory_fallback()

    old_carrier = _carrier_with_sources([("1", "old.pdf", "OLD " * 1000)])
    new_carrier = _carrier_with_sources([("2", "new.pdf", "NEW " * 1000)])

    messages = [
        _Msg("user", old_carrier),
        _Msg("assistant", "خلاصه old"),
        _Msg("user", new_carrier),
    ]
    keep, allowed, reason = resolve_turn_file_scope([], messages)
    assert keep is True
    assert "new.pdf" in allowed
    assert "old.pdf" not in allowed
    assert reason == "last-msg-fresh-source"


def test_followup_question_without_file_does_not_leak_history():
    """سؤال متنی بدون فایل — نباید فایل قدیمی history نشت کند."""
    reset_memory_fallback()

    carrier = _carrier_with_sources([("1", "doc.pdf", "BODY " * 1000)])
    turn1 = [_Msg("user", carrier)]
    remember_conversation_sources(None, turn1)

    messages = [
        _Msg("user", carrier),
        _Msg("assistant", "خلاصه"),
        _Msg("user", "یک سؤال نامرتبط بدون فایل"),
    ]
    keep, allowed, reason = resolve_turn_file_scope([], messages)
    assert keep is False
    assert reason == "no-new-attach"


def test_files_attached_true_when_carrier_matches():
    reset_memory_fallback()
    reset_conversation_sources(messages=[_Msg("user", OWUI_TEMPLATE)])
    messages = [
        _Msg("user", OWUI_TEMPLATE),
        _Msg("user", "What is in all three files?"),
    ]
    keep, allowed, reason = resolve_turn_file_scope([], messages)
    assert keep is True
    assert "file_a.txt" in allowed
    assert reason.startswith("carrier-merge:")
    assert files_attached_this_turn([], messages)


def test_new_sources_detected_when_openwebui_updates_first_message():
    carrier_v1 = _carrier_with_sources([("1", "old.ovpn", "OLD")])
    carrier_v2 = _carrier_with_sources([
        ("1", "old.ovpn", "OLD"),
        ("2", "new.ovpn", "NEW"),
    ])

    reset_conversation_sources(messages=[_Msg("user", carrier_v1)])

    messages_turn1 = [_Msg("user", carrier_v1)]
    remember_conversation_sources(None, messages_turn1)

    messages_turn3 = [
        _Msg("user", carrier_v2),
        _Msg("assistant", "done"),
        _Msg("user", "سؤال اول"),
        _Msg("assistant", "ok"),
        _Msg("user", "فایل جدید را بخوان"),
    ]
    delta = sources_delta_for_conversation(None, messages_turn3)
    assert "new.ovpn" in delta
    assert "2" in delta

    keep, allowed, reason = resolve_turn_file_scope([], messages_turn3)
    assert keep is True
    assert "new.ovpn" in allowed
    assert reason.startswith("conv-delta:")

    content_idx = find_file_content_index(messages_turn3, 4, allowed)
    assert content_idx == 0


def test_followup_with_accumulated_sources_in_last_message_is_not_attach():
    reset_conversation_sources(messages=[_Msg("user", OWUI_TEMPLATE)])
    remember_conversation_sources(None, [_Msg("user", OWUI_TEMPLATE)])

    accumulated_last = OWUI_TEMPLATE.replace(
        "<user_query>\nWhat is in all three files?\n</user_query>",
        "<user_query>\nدر مورد فایل های فرستاده شده صحبت کن\n</user_query>",
    )
    messages = [
        _Msg("user", OWUI_TEMPLATE),
        _Msg("assistant", "answer"),
        _Msg("user", accumulated_last),
    ]
    assert not files_attached_this_turn([], messages)
    keep, allowed, reason = resolve_turn_file_scope([], messages)
    assert keep is False
    assert allowed == set()


def test_single_turn_bypass_markup_without_source_tags_keeps_pdf_body():
    """OpenWebUI bypass: متن PDF بدون تگ <source> داخل قالب Task."""
    pdf_body = "متن مقاله PDF " * 300
    payload = (
        "### Task:\nRespond using context.\n\n"
        f"{pdf_body}\n\n"
        "<user_query>\nاین مقاله را خلاصه کن\n</user_query>\n"
    )
    scoped, _ = scope_message_content(
        payload,
        is_current_turn=True,
        allowed_names=set(),
        keep_files=True,
    )
    assert "متن مقاله PDF" in scoped
    assert "خلاصه کن" in scoped
    assert len(scoped) > 2000

    messages = [_Msg("user", payload)]
    keep, allowed, reason = resolve_turn_file_scope([], messages)
    assert keep is True
    assert reason == "single-turn-markup"


def test_single_turn_file_part_in_multipart():
    from app.core.attachment_cache import reset_memory_fallback
    reset_memory_fallback()

    pdf_text = "Chapter one content " * 200
    content = [
        {"type": "text", "text": "<user_query>خلاصه مقاله</user_query>"},
        {"type": "file", "file": {"filename": "paper.pdf", "content": pdf_text}},
    ]
    messages = [_Msg("user", content)]
    keep, allowed, reason = resolve_turn_file_scope([], messages)
    assert keep is True
    assert reason in {"single-turn-file-part", "conv-delta:"} or reason.startswith("conv-delta:")

    scoped, _ = scope_message_content(
        content,
        is_current_turn=True,
        allowed_names=set(),
        keep_files=True,
    )
    assert isinstance(scoped, list)
    texts = [p.get("text", "") for p in scoped if isinstance(p, dict)]
    file_texts = [
        p.get("file", {}).get("content", "")
        for p in scoped
        if isinstance(p, dict) and p.get("type") == "file"
    ]
    combined = "\n".join(texts + file_texts)
    assert "Chapter one content" in combined


def test_single_turn_inline_attach():
    big = "LINE\n" * 500 + "END"
    messages = [_Msg("user", big)]
    keep, allowed, reason = resolve_turn_file_scope([], messages)
    assert keep is True
    assert reason in {"single-turn-inline", "new-inline-file"}


class _ImgMsg:
    def __init__(self, role, content, images=None):
        self.role = role
        self.content = content
        self.images = images or []


def _image_data_url(tag: str) -> str:
    return "data:image/png;base64," + ("A" * 50) + tag


def test_image_in_images_field_is_attach():
    reset_conversation_sources(messages=[_ImgMsg("user", "")])
    messages = [_ImgMsg("user", "این عکس را بخوان", images=[_image_data_url("X")])]
    assert files_attached_this_turn([], messages)
    keep, allowed, reason = resolve_turn_file_scope([], messages)
    assert keep is True


def test_image_in_content_array_is_attach():
    content = [
        {"type": "text", "text": "این عکس را توضیح بده"},
        {"type": "image_url", "image_url": {"url": _image_data_url("Y")}},
    ]
    messages = [_Msg("user", content)]
    reset_conversation_sources(messages=messages)
    assert files_attached_this_turn([], messages)
    keep, allowed, reason = resolve_turn_file_scope([], messages)
    assert keep is True


def test_old_image_not_reattached_on_text_followup():
    img = _image_data_url("Z")
    turn1 = [_ImgMsg("user", "عکس را بخوان", images=[img])]
    reset_conversation_sources(messages=turn1)
    remember_conversation_sources(None, turn1)

    followup = [
        _ImgMsg("user", "عکس را بخوان", images=[img]),
        _Msg("assistant", "متن عکس ..."),
        _Msg("user", "حالا خلاصه کن"),
    ]
    assert not files_attached_this_turn([], followup)
    keep, allowed, reason = resolve_turn_file_scope([], followup)
    assert keep is False
    assert current_turn_images(None, followup) == []


def test_stale_image_in_last_message_not_reattached():
    """OpenWebUI گاهی تصویر قدیمی را در پیام آخر نگه می‌دارد — نباید دوباره attach شود."""
    reset_memory_fallback()
    img = _image_data_url("stale")
    turn1 = [_ImgMsg("user", "عکس را بخوان", images=[img])]
    reset_conversation_sources(messages=turn1)
    remember_conversation_sources(None, turn1)

    followup = [
        _ImgMsg("user", "عکس را بخوان", images=[img]),
        _Msg("assistant", "متن استخراج‌شده"),
        _ImgMsg("user", "فقط خلاصه کن", images=[img]),
    ]
    assert not files_attached_this_turn([], followup)
    keep, allowed, reason = resolve_turn_file_scope([], followup)
    assert keep is False
    assert allowed == set()
    assert reason == "no-new-attach"
    assert current_turn_images(None, followup) == []


def test_new_image_detected_in_multiturn():
    img1 = _image_data_url("1")
    img2 = _image_data_url("2")
    turn1 = [_ImgMsg("user", "عکس اول", images=[img1])]
    reset_conversation_sources(messages=turn1)
    remember_conversation_sources(None, turn1)

    turn2 = [
        _ImgMsg("user", "عکس اول", images=[img1]),
        _Msg("assistant", "..."),
        _ImgMsg("user", "این عکس دوم را هم بخوان", images=[img2]),
    ]
    keep, allowed, reason = resolve_turn_file_scope([], turn2)
    assert keep is True
    new_imgs = current_turn_images(None, turn2)
    assert img2 in new_imgs
    assert img1 not in new_imgs


def test_conversation_key_stable_not_python_hash():
    """کلید مکالمه بین workerها یکسان باشد (نه hash() تصادفی Python)."""
    messages = [_Msg("user", OWUI_TEMPLATE)]
    k1 = conversation_key(None, messages)
    k2 = conversation_key(None, messages)
    assert k1 == k2
    assert k1.startswith("anchor:")
    assert "anchor:-" not in (k1 or "")  # hash() منفی می‌دهد؛ SHA256 نه


def test_multiturn_pdf_then_ovpn_sources_only_new_in_allowed():
    """سناریوی کاربر: PDF → متن → ovpn+sources.list — فقط فایل‌های جدید در allowed."""
    reset_memory_fallback()

    pdf_carrier = _carrier_with_sources([
        ("1", "1664710902_F2472-Farsi-e-tarjom.pdf", "PDF BODY"),
    ])
    all_carrier = _carrier_with_sources([
        ("1", "1664710902_F2472-Farsi-e-tarjom.pdf", "PDF BODY"),
        ("2", "goodarzi.payeh_2.ovpn", "OVPN BODY"),
        ("3", "sources.list", "SOURCES BODY"),
    ])

    turn1 = [_Msg("user", pdf_carrier)]
    reset_conversation_sources(messages=turn1)
    remember_conversation_sources(None, turn1)

    turn2 = [
        _Msg("user", pdf_carrier),
        _Msg("assistant", "خلاصه pdf"),
        _Msg("user", "سؤال متنی بدون فایل"),
    ]
    remember_conversation_sources(None, turn2)
    keep2, _, reason2 = resolve_turn_file_scope([], turn2)
    assert keep2 is False
    assert reason2 == "no-new-attach"

    turn3 = [
        _Msg("user", all_carrier),
        _Msg("assistant", "خلاصه pdf"),
        _Msg("user", "سؤال متنی"),
        _Msg("assistant", "ok"),
        _Msg("user", "این دو فایل جدید را بخوان"),
    ]
    delta = attachments_delta_for_conversation(None, turn3)
    assert "goodarzi.payeh_2.ovpn" in delta
    assert "sources.list" in delta
    assert "1664710902_F2472-Farsi-e-tarjom.pdf" not in delta

    keep3, allowed3, reason3 = resolve_turn_file_scope([], turn3)
    assert keep3 is True
    assert reason3.startswith("conv-delta:")
    assert "goodarzi.payeh_2.ovpn" in allowed3
    assert "sources.list" in allowed3
    assert "1664710902_F2472-Farsi-e-tarjom.pdf" not in allowed3
    assert not any(a.startswith("file:") for a in allowed3)


def test_file_fingerprint_bootstrap_not_redetected():
    """fingerprintهای file: در bootstrap — دوباره در delta نیایند."""
    reset_memory_fallback()

    pdf_text = "PDF content block " * 200
    carrier = (
        "### Task:\nRespond.\n\n"
        f"{pdf_text}\n\n"
        "<user_query>\nخلاصه کن\n</user_query>\n"
    )
    turn1 = [_Msg("user", carrier)]
    reset_conversation_sources(messages=turn1)
    remember_conversation_sources(None, turn1)

    turn2 = [
        _Msg("user", carrier),
        _Msg("assistant", "done"),
        _Msg("user", "سؤال بعدی"),
    ]
    delta = attachments_delta_for_conversation(None, turn2)
    assert not any(a.startswith("file:") for a in delta)
