"""
فیلتر محتوای فایل OpenWebUI — رفتار شبیه ChatGPT / DeepSeek.

OpenWebUI با bypass روشن، فایل‌های کل مکالمه را در درخواست جمع می‌کند.
این ماژول فقط فایل‌های «همین نوبت» را نگه می‌دارد:
  - پیام‌های قبلی: فقط متن سؤال کاربر (بدون محتوای فایل)
  - نوبت بدون attach جدید: هیچ فایلی به مدل نرود
  - نوبت با attach جدید: فقط فایل‌هایی که در این درخواست تازه ظاهر شده‌اند
"""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import PurePosixPath

logger = logging.getLogger(__name__)

# متن کوتاه‌تر از این در تاریخچه «سؤال کاربر» تلقی می‌شود؛ بلندتر = احتمالاً فایل inline
_USER_TEXT_MAX_CHARS = 2000

_SOURCE_RE = re.compile(
    r"<source\b([^>]*)>(.*?)</source>",
    re.DOTALL | re.IGNORECASE,
)
_CONTEXT_RE = re.compile(r"<context>.*?</context>", re.DOTALL | re.IGNORECASE)
_USER_QUERY_RE = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.DOTALL | re.IGNORECASE)
_TASK_MARKER = re.compile(r"###\s*Task:", re.IGNORECASE)


def _basename(name: str) -> str:
    return PurePosixPath(name.replace("\\", "/")).name.strip()


def _source_names_and_ids(text: str) -> tuple[set[str], set[str]]:
    names: set[str] = set()
    ids: set[str] = set()
    for sm in _SOURCE_RE.finditer(text):
        attrs = sm.group(1)
        nm = re.search(r"""name=["']([^"']+)["']""", attrs, re.IGNORECASE)
        idm = re.search(r"""id=["']([^"']+)["']""", attrs, re.IGNORECASE)
        if nm:
            names.add(_basename(nm.group(1)))
        if idm:
            ids.add(idm.group(1).strip())
    return names, ids


def all_source_names(text: str) -> set[str]:
    """همه‌ی نام/id منبع‌های داخل یک پیام."""
    names, ids = _source_names_and_ids(text)
    return names | ids


def _name_matches(source_name: str, source_id: str, allowed: set[str]) -> bool:
    if not allowed:
        return False
    if source_id and source_id in allowed:
        return True
    src = _basename(source_name)
    for a in allowed:
        cand = _basename(a)
        if src == cand or src.endswith(cand) or cand.endswith(src):
            return True
    return False


def extract_user_query(text: str) -> str:
    """متن واقعی سؤال کاربر را از قالب OpenWebUI استخراج می‌کند."""
    m = _USER_QUERY_RE.search(text)
    if m:
        return m.group(1).strip()

    if _TASK_MARKER.search(text):
        stripped = _CONTEXT_RE.sub("", text)
        stripped = re.sub(r"</?user_query>", "", stripped, flags=re.IGNORECASE).strip()
        lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
        user_lines = [
            ln for ln in lines
            if not ln.startswith("###") and "Guidelines" not in ln and "citation" not in ln.lower()
        ]
        if user_lines:
            return user_lines[-1]

    return text.strip()


def filter_sources(text: str, allowed_names: set[str]) -> str:
    """
    بلوک‌های <source> را بر اساس نام فایل فیلتر می‌کند.
    allowed_names خالی = حذف کامل context و برگرداندن فقط user_query.
    """
    if not text:
        return ""

    if not allowed_names:
        without_ctx = _CONTEXT_RE.sub("", text)
        query = extract_user_query(without_ctx)
        return query if query else without_ctx.strip()

    def _rebuild_context(match: re.Match) -> str:
        kept: list[str] = []
        for sm in _SOURCE_RE.finditer(match.group(0)):
            attrs, _body = sm.group(1), sm.group(2)
            name_m = re.search(r"""name=["']([^"']+)["']""", attrs, re.IGNORECASE)
            id_m = re.search(r"""id=["']([^"']+)["']""", attrs, re.IGNORECASE)
            sname = name_m.group(1) if name_m else ""
            sid = id_m.group(1) if id_m else ""
            if _name_matches(sname, sid, allowed_names):
                kept.append(sm.group(0))
        if kept:
            return "<context>\n" + "\n".join(kept) + "\n</context>"
        return ""

    rebuilt = _CONTEXT_RE.sub(_rebuild_context, text)
    if _TASK_MARKER.search(rebuilt):
        return rebuilt.strip()
    return rebuilt.strip()


def _has_file_markup(text: str) -> bool:
    return (
        "<source" in text.lower()
        or "<context>" in text.lower()
        or _TASK_MARKER.search(text) is not None
    )


def _looks_like_inline_file(text: str) -> bool:
    """متن بلند بدون تگ XML — معمولاً محتوای کامل فایل inline از OpenWebUI (bypass)."""
    return len(text) > _USER_TEXT_MAX_CHARS


def _scope_plain_text(
    text: str,
    *,
    is_current_turn: bool,
    allowed_names: set[str],
    keep_files: bool = True,
) -> str:
    if not text:
        return ""

    has_markup = _has_file_markup(text)

    if not is_current_turn:
        if has_markup:
            return extract_user_query(filter_sources(text, set()))
        if len(text) <= _USER_TEXT_MAX_CHARS:
            return text.strip()
        return extract_user_query(text)

    if not keep_files:
        if has_markup or _looks_like_inline_file(text):
            return extract_user_query(filter_sources(text, set()))
        return text.strip()

    if has_markup:
        effective = allowed_names or all_source_names(text)
        if effective:
            return filter_sources(text, effective)
        if keep_files and is_current_turn:
            query_only = extract_user_query(filter_sources(text, set()))
            # OpenWebUI bypass: متن PDF/فایل گاهی بدون تگ <source> داخل قالب Task تزریق می‌شود
            if len(text.strip()) > max(len(query_only) + 200, _USER_TEXT_MAX_CHARS):
                return text.strip()
        return extract_user_query(filter_sources(text, set()))

    if _looks_like_inline_file(text):
        return text.strip()

    return text.strip()


def _scope_multipart(
    parts: list,
    *,
    is_current_turn: bool,
    allowed_names: set[str],
    keep_files: bool = True,
) -> list:
    scoped: list = []
    for part in parts:
        if not isinstance(part, dict):
            if isinstance(part, str) and part.strip():
                scoped.append(part)
            continue

        ptype = part.get("type")
        if ptype == "text" or (ptype is None and "text" in part):
            text = part.get("text", "") or ""
            cleaned = _scope_plain_text(
                text,
                is_current_turn=is_current_turn,
                allowed_names=allowed_names,
                keep_files=keep_files,
            )
            if cleaned:
                scoped.append({"type": "text", "text": cleaned})
        elif ptype == "image_url":
            if is_current_turn and keep_files:
                scoped.append(part)
        elif ptype == "file":
            if is_current_turn and keep_files:
                scoped.append(part)
        elif is_current_turn and keep_files:
            scoped.append(part)
    return scoped


def scope_message_content(
    raw,
    *,
    is_current_turn: bool,
    allowed_names: set[str],
    keep_files: bool = True,
) -> tuple:
    """محتوای خام پیام را محدود می‌کند."""
    if isinstance(raw, list):
        return _scope_multipart(
            raw, is_current_turn=is_current_turn, allowed_names=allowed_names, keep_files=keep_files
        ), True

    if isinstance(raw, str):
        return _scope_plain_text(
            raw, is_current_turn=is_current_turn, allowed_names=allowed_names, keep_files=keep_files
        ), True

    if raw:
        return _scope_plain_text(
            str(raw), is_current_turn=is_current_turn, allowed_names=allowed_names, keep_files=keep_files
        ), True

    return "", True


def _message_role(message) -> str:
    if hasattr(message, "role"):
        return message.role
    if isinstance(message, dict):
        return message.get("role", "")
    return ""


def _last_user_index(messages) -> int:
    for i in range(len(messages) - 1, -1, -1):
        if _message_role(messages[i]) == "user":
            return i
    return -1


def _get_raw_content(message) -> object:
    if hasattr(message, "content"):
        return message.content
    if isinstance(message, dict):
        return message.get("content", "")
    return ""


def _message_has_images(message) -> bool:
    return len(_message_image_urls(message)) > 0


def _message_image_urls(message) -> list[str]:
    """
    همه‌ی data-URL تصاویر یک پیام را برمی‌گرداند.
    OpenWebUI تصویر را به دو شکل می‌فرستد:
      ۱) فیلد `images: [...]`
      ۲) آرایه‌ی content با partهای {"type":"image_url", "image_url":{"url":"data:image..."}}
    """
    urls: list[str] = []

    if hasattr(message, "images"):
        images = message.images
    elif isinstance(message, dict):
        images = message.get("images", [])
    else:
        images = []
    if isinstance(images, list):
        for img in images:
            if isinstance(img, str) and img.startswith("data:image"):
                urls.append(img)

    raw = _get_raw_content(message)
    if isinstance(raw, list):
        for part in raw:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "image_url":
                url_data = part.get("image_url", {})
                url = url_data.get("url", "") if isinstance(url_data, dict) else str(url_data)
                if isinstance(url, str) and url.startswith("data:image"):
                    urls.append(url)
    return urls


def _image_fingerprint(url: str) -> str:
    body = url.split(",", 1)[1] if "," in url else url
    return "img:" + hashlib.md5(body.encode("utf-8", errors="ignore")).hexdigest()


def _message_image_fingerprints(message) -> set[str]:
    return {_image_fingerprint(u) for u in _message_image_urls(message)}


def _file_part_text(part: dict) -> str:
    """متن استخراج‌شده از part نوع file در payload چندبخشی OpenWebUI."""
    if not isinstance(part, dict):
        return ""
    file_obj = part.get("file") if part.get("type") == "file" else part
    if not isinstance(file_obj, dict):
        return ""
    for key in ("content", "data", "text", "value"):
        val = file_obj.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _message_file_texts(message) -> list[str]:
    raw = _get_raw_content(message)
    if not isinstance(raw, list):
        return []
    return [t for p in raw if isinstance(p, dict) for t in [_file_part_text(p)] if t]


def _message_has_file_parts(message) -> bool:
    return bool(_message_file_texts(message))


def _file_part_fingerprint(text: str) -> str:
    return "file:" + hashlib.md5(text[:2000].encode("utf-8", errors="ignore")).hexdigest()


def _message_file_fingerprints(message) -> set[str]:
    return {_file_part_fingerprint(t) for t in _message_file_texts(message)}


def _raw_to_text(raw) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts = []
        for p in raw:
            if isinstance(p, dict):
                if p.get("text"):
                    parts.append(str(p["text"]))
                file_text = _file_part_text(p)
                if file_text:
                    parts.append(file_text)
        return "\n".join(parts)
    return str(raw) if raw else ""


def _sources_before_index(messages, before_idx: int) -> set[str]:
    """همه‌ی sourceهای موجود در پیام‌های user قبل از before_idx."""
    names: set[str] = set()
    for i in range(before_idx):
        if _message_role(messages[i]) != "user":
            continue
        names |= all_source_names(_raw_to_text(_get_raw_content(messages[i])))
    return names


def _all_user_sources(messages) -> set[str]:
    names: set[str] = set()
    for i, m in enumerate(messages):
        if _message_role(m) != "user":
            continue
        names |= all_source_names(_raw_to_text(_get_raw_content(m)))
    return names


def _images_before_index(messages, before_idx: int) -> set[str]:
    fps: set[str] = set()
    for i in range(before_idx):
        if _message_role(messages[i]) != "user":
            continue
        fps |= _message_image_fingerprints(messages[i])
    return fps


def _file_fingerprints_before_index(messages, before_idx: int) -> set[str]:
    fps: set[str] = set()
    for i in range(before_idx):
        if _message_role(messages[i]) != "user":
            continue
        fps |= _message_file_fingerprints(messages[i])
    return fps


def _attachments_before_index(messages, before_idx: int) -> set[str]:
    return (
        _sources_before_index(messages, before_idx)
        | _images_before_index(messages, before_idx)
        | _file_fingerprints_before_index(messages, before_idx)
    )


def _allowed_names_from_delta(delta: set[str]) -> set[str]:
    """نام/id برای filter_sources — fingerprintهای img:/file: فقط برای تشخیص attach."""
    return {a for a in delta if not a.startswith(("img:", "file:"))}


def _all_user_images(messages) -> set[str]:
    fps: set[str] = set()
    for m in messages:
        if _message_role(m) != "user":
            continue
        fps |= _message_image_fingerprints(m)
    return fps


def _all_user_attachments(messages) -> set[str]:
    """امضای همه‌ی ضمائم کاربر: نام/id فایل‌ها + اثرانگشت تصاویر + partهای file."""
    names = _all_user_sources(messages) | _all_user_images(messages)
    for m in messages:
        if _message_role(m) != "user":
            continue
        names |= _message_file_fingerprints(m)
    return names


# حافظه‌ی ضمائم: Redis (با fallback in-memory) — app/core/attachment_cache.py
from app.core.attachment_cache import (
    get_seen_attachments,
    set_seen_attachments,
    bootstrap_seen_attachments,
    delete_seen_attachments,
    reset_memory_fallback,
)


def _stable_anchor_hash(anchor: str) -> str:
    """هش پایدار بین process/worker — برخلاف hash() داخلی Python."""
    return hashlib.sha256(anchor.encode("utf-8")).hexdigest()[:16]


def _derive_chat_key(messages) -> str | None:
    """
    وقتی OpenWebUI conversation_id نمی‌فرستد، از اولین پیام user به‌عنوان لنگر مکالمه استفاده می‌کنیم.
    در چت‌های چندنوبتی OpenWebUI معمولاً msg[0] ثابت می‌ماند و فقط فایل‌های جدید به آن اضافه می‌شوند.
    """
    for m in messages:
        if _message_role(m) != "user":
            continue
        text = _raw_to_text(_get_raw_content(m))
        anchor = extract_user_query(text)[:300] or text[:300]
        if anchor:
            return f"anchor:{_stable_anchor_hash(anchor)}"
    return None


def conversation_key(conversation_id, messages=None) -> str | None:
    """کلید Redis کش ضمائم — برای لاگ و تست."""
    return _conversation_key(conversation_id, messages)


def _conversation_key(conversation_id, messages=None) -> str | None:
    if conversation_id is not None:
        text = str(conversation_id).strip()
        if text:
            return f"id:{text}"
    if messages is not None:
        return _derive_chat_key(messages)
    return None


def attachments_delta_for_conversation(conversation_id, messages) -> set[str]:
    """
    ضمائمی (source + image) که نسبت به آخرین درخواست همین مکالمه تازه ظاهر شده‌اند.
    اگر cache خالی باشد، ضمائم قبل از آخرین پیام user بوت‌استرپ می‌شوند.
    """
    last_idx = _last_user_index(messages)
    current = _all_user_attachments(messages)
    key = _conversation_key(conversation_id, messages)
    if not key:
        return current - _attachments_before_index(messages, last_idx)
    bootstrap_seen_attachments(key, _attachments_before_index(messages, last_idx))
    previous = get_seen_attachments(key) or set()
    return current - previous


def sources_delta_for_conversation(conversation_id, messages) -> set[str]:
    """فقط نام/id فایل‌های متنی جدید این نوبت (بدون تصاویر)."""
    return {a for a in attachments_delta_for_conversation(conversation_id, messages) if not a.startswith("img:")}


def current_turn_images(conversation_id, messages) -> list[str]:
    """data-URL تصاویری که در این نوبت تازه attach شده‌اند — برای OCR."""
    delta = attachments_delta_for_conversation(conversation_id, messages)
    new_fps = {a for a in delta if a.startswith("img:")}
    if not new_fps:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for m in messages:
        if _message_role(m) != "user":
            continue
        for url in _message_image_urls(m):
            fp = _image_fingerprint(url)
            if fp in new_fps and fp not in seen:
                seen.add(fp)
                result.append(url)
    return result


def remember_conversation_sources(conversation_id, messages) -> None:
    """وضعیت ضمائم را بعد از پردازش درخواست ذخیره می‌کند."""
    key = _conversation_key(conversation_id, messages)
    if key:
        set_seen_attachments(key, _all_user_attachments(messages))


def reset_conversation_sources(conversation_id=None, messages=None) -> None:
    """برای تست یا شروع مجدد مکالمه."""
    key = _conversation_key(conversation_id, messages)
    if key:
        delete_seen_attachments(key)


def _new_sources_this_turn(messages) -> set[str]:
    """
    sourceهایی که در این درخواست تازه ظاهر شده‌اند.
    OpenWebUI معمولاً فایل‌های جدید را به پیام حامل قدیمی (مثلاً msg[0]) اضافه می‌کند،
    نه لزوماً به آخرین پیام.
    """
    last_idx = _last_user_index(messages)
    if last_idx < 0:
        return set()
    before_last = _sources_before_index(messages, last_idx)
    return _all_user_sources(messages) - before_last


def _inline_fingerprint(text: str) -> tuple[int, str]:
    return len(text), text[:500]


def _has_new_inline_file(messages, last_idx: int) -> bool:
    """فایل inline بدون تگ XML که قبلاً در مکالمه نبوده."""
    text = _raw_to_text(_get_raw_content(messages[last_idx]))
    if not _looks_like_inline_file(text) or _has_file_markup(text):
        return False
    fp = _inline_fingerprint(text)
    for i in range(last_idx):
        if _message_role(messages[i]) != "user":
            continue
        prev = _raw_to_text(_get_raw_content(messages[i]))
        if _inline_fingerprint(prev) == fp:
            return False
    return True


def carrier_matches_last_question(carrier_raw, last_raw) -> bool:
    """
    OpenWebUI وقتی فایل attach می‌شود، همان سؤال را هم در پیام حامل و هم در
    آخرین پیام می‌گذارد.
    """
    carrier_q = extract_user_query(_raw_to_text(carrier_raw)).strip()
    last_q = _raw_to_text(last_raw).strip()
    if not carrier_q or not last_q:
        return False
    return carrier_q == last_q or last_q in carrier_q or carrier_q in last_q


def find_turn_carrier_for_merge(messages, last_idx: int) -> int:
    """
    پیام user قبل از آخرین پیام که فایل دارد و سؤالش با آخرین پیام یکی است.
    الگوی رایج: فایل در پیام حامل، سؤال کوتاه در آخرین پیام.
    """
    if last_idx < 0:
        return -1
    last_raw = _get_raw_content(messages[last_idx])
    best = -1
    for i in range(last_idx):
        if _message_role(messages[i]) != "user":
            continue
        carrier_text = _raw_to_text(_get_raw_content(messages[i]))
        if not (_has_file_markup(carrier_text) or _looks_like_inline_file(carrier_text)):
            continue
        if carrier_matches_last_question(_get_raw_content(messages[i]), last_raw):
            best = i
    return best


def find_context_carrier_index(messages) -> int:
    """قدیمی‌ترین/بلندترین پیام حامل فایل — فقط برای لاگ."""
    best_idx = -1
    best_len = 0
    for i, m in enumerate(messages):
        if _message_role(m) != "user":
            continue
        text = _raw_to_text(_get_raw_content(m))
        if _has_file_markup(text) or _looks_like_inline_file(text):
            if len(text) > best_len:
                best_idx = i
                best_len = len(text)
    return best_idx


def files_attached_this_turn(files, messages, conversation_id=None) -> bool:
    """آیا کاربر در همین نوبت فایل/تصویر جدید attach کرده؟"""
    if file_names_from_request(files):
        return True

    last_idx = _last_user_index(messages)
    if last_idx < 0:
        return False

    if attachments_delta_for_conversation(conversation_id, messages):
        return True

    if find_turn_carrier_for_merge(messages, last_idx) >= 0:
        return True

    if _has_new_inline_file(messages, last_idx):
        return True

    user_count = sum(1 for m in messages if _message_role(m) == "user")
    if user_count == 1:
        text = _raw_to_text(_get_raw_content(messages[last_idx]))
        if _has_file_markup(text) or _looks_like_inline_file(text):
            return True
        if _message_image_urls(messages[last_idx]):
            return True

    return False


def find_file_content_index(messages, last_idx: int, allowed: set[str]) -> int:
    """پیامی که محتوای فایل‌های allowed در آن قرار دارد."""
    if not allowed:
        last_text = _raw_to_text(_get_raw_content(messages[last_idx]))
        if _message_has_file_parts(messages[last_idx]):
            return last_idx
        if _looks_like_inline_file(last_text) and not _has_file_markup(last_text):
            return last_idx
        return -1

    if last_idx >= 0:
        last_names = all_source_names(_raw_to_text(_get_raw_content(messages[last_idx])))
        if allowed & last_names:
            return last_idx

    best = -1
    best_overlap = 0
    for i, m in enumerate(messages):
        if _message_role(m) != "user":
            continue
        names = all_source_names(_raw_to_text(_get_raw_content(m)))
        overlap = len(allowed & names)
        if overlap > best_overlap:
            best = i
            best_overlap = overlap
    return best


def resolve_turn_file_scope(files, messages, conversation_id=None) -> tuple[bool, set[str], str]:
    """
    (keep_files, allowed_names, reason) برای همین نوبت.
    keep_files=False → هیچ فایلی به مدل نرود (مثل ChatGPT بدون attach).
    """
    last_idx = _last_user_index(messages)

    names = file_names_from_request(files)
    if names:
        return True, names, "request.files"

    if last_idx < 0:
        return False, set(), "no-user-message"

    full_delta = attachments_delta_for_conversation(conversation_id, messages)
    new_images = {a for a in full_delta if a.startswith("img:")}
    new_non_image = full_delta - new_images
    allowed_names = _allowed_names_from_delta(new_non_image)
    if new_non_image:
        return True, allowed_names, f"conv-delta:{sorted(new_non_image)}"
    if new_images:
        return True, set(), f"new-images:{len(new_images)}"

    carrier_idx = find_turn_carrier_for_merge(messages, last_idx)
    if carrier_idx >= 0:
        carrier_allowed = all_source_names(_raw_to_text(_get_raw_content(messages[carrier_idx])))
        return True, carrier_allowed, f"carrier-merge:{carrier_idx}"

    if _has_new_inline_file(messages, last_idx):
        return True, set(), "new-inline-file"

    user_count = sum(1 for m in messages if _message_role(m) == "user")
    if user_count == 1:
        if _message_has_file_parts(messages[last_idx]):
            return True, set(), "single-turn-file-part"
        text = _raw_to_text(_get_raw_content(messages[last_idx]))
        if _has_file_markup(text):
            return True, all_source_names(text), "single-turn-markup"
        if _looks_like_inline_file(text):
            return True, set(), "single-turn-inline"
        if _message_image_urls(messages[last_idx]):
            return True, set(), "single-turn-image"

    return False, set(), "no-new-attach"


def should_merge_carrier(files, messages, last_user_idx: int, carrier_idx: int) -> bool:
    """آیا محتوای فایل از پیام حامل باید به آخرین پیام merge شود؟"""
    if carrier_idx < 0 or last_user_idx < 0 or carrier_idx == last_user_idx:
        return False
    if file_names_from_request(files):
        return True
    carrier_raw = _get_raw_content(messages[carrier_idx])
    last_raw = _get_raw_content(messages[last_user_idx])
    return carrier_matches_last_question(carrier_raw, last_raw)


def extract_carrier_file_content(raw, allowed_names: set[str], keep_files: bool = True) -> str:
    """محتوای فایل از پیام حامل — بدون تبدیل به سؤال کوتاه."""
    if isinstance(raw, list):
        parts = _scope_multipart(
            raw, is_current_turn=True, allowed_names=allowed_names, keep_files=keep_files
        )
        texts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")]
        file_texts = [_file_part_text(p) for p in parts if isinstance(p, dict)]
        texts.extend(t for t in file_texts if t)
        return "\n\n".join(t for t in texts if t.strip())
    if isinstance(raw, str):
        return _scope_plain_text(
            raw, is_current_turn=True, allowed_names=allowed_names, keep_files=keep_files
        )
    return _scope_plain_text(
        str(raw), is_current_turn=True, allowed_names=allowed_names, keep_files=keep_files
    )


def file_names_from_request(files) -> set[str]:
    """نام فایل‌های attach‌شده در همین درخواست (فیلد files در body)."""
    names: set[str] = set()
    for f in files or []:
        name = getattr(f, "name", None) or (f.get("name") if isinstance(f, dict) else None)
        fid = getattr(f, "id", None) or (f.get("id") if isinstance(f, dict) else None)
        if name:
            names.add(_basename(str(name)))
        if fid:
            names.add(str(fid).strip())
    return names


# سازگاری با کد قدیمی
def has_attachments_this_turn(files, messages, last_user_idx: int) -> bool:
    return files_attached_this_turn(files, messages)
