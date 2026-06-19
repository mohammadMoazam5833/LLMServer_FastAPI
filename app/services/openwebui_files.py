"""
واکشی محتوای فایل از OpenWebUI وقتی Bypass فعال است ولی API خارجی
فقط متن سؤال را فوروارد می‌کند (بدون inject در messages).

OpenWebUI فایل را در :3000/api/v1/files نگه می‌دارد؛ gateway با این ماژول
از /api/v1/files/{id}/data/content متن استخراج‌شده را می‌گیرد.
"""
from __future__ import annotations

import io
import logging
import re
import unicodedata
from typing import Any

import httpx

from app.config import get_settings
from app.schemas.schemas import ChatCompletionRequest, ChatMessage
from app.core.attachment_cache import get_seen_attachments

settings = get_settings()
logger = logging.getLogger(__name__)

OWUI_CHAT_ID_HEADERS = ("X-OpenWebUI-Chat-Id", "x-openwebui-chat-id")

_SOURCE_RE = re.compile(
    r"<source\b([^>]*)>(.*?)</source>",
    re.DOTALL | re.IGNORECASE,
)
_MIN_INLINE_SOURCE_CHARS = 200


def _file_id_and_name(item: dict) -> tuple[str | None, str | None]:
    if not isinstance(item, dict):
        return None, None
    fid = item.get("id") or item.get("file_id")
    name = item.get("name") or item.get("filename")
    nested = item.get("file")
    if isinstance(nested, dict):
        fid = fid or nested.get("id")
        name = name or nested.get("name") or nested.get("filename")
    if fid is not None:
        fid = str(fid).strip()
    if name is not None:
        name = str(name).strip()
    return fid or None, name or None


def extract_openwebui_file_refs(raw: dict) -> list[tuple[str, str]]:
    """(file_id, display_name) از payload خام OpenWebUI."""
    seen: set[str] = set()
    refs: list[tuple[str, str]] = []

    def add_from_list(items: Any) -> None:
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            fid, name = _file_id_and_name(item)
            if fid and fid not in seen:
                seen.add(fid)
                refs.append((fid, name or fid))

    add_from_list(raw.get("files"))
    metadata = raw.get("metadata")
    if isinstance(metadata, dict):
        add_from_list(metadata.get("files"))

    for msg in raw.get("messages") or []:
        if not isinstance(msg, dict):
            continue
        add_from_list(msg.get("files"))
        msg_meta = msg.get("metadata")
        if isinstance(msg_meta, dict):
            add_from_list(msg_meta.get("files"))

    return refs


def _is_openwebui_file_item(item: dict) -> bool:
    return item.get("type") == "file" or isinstance(item.get("file"), dict)


def sanitize_raw_for_validation(raw: dict) -> dict:
    """
    فایل‌های OpenWebUI (type=file با nested file.id) را از body.files حذف می‌کند
    تا Pydantic خطا ندهد و RAG اشتباهی UUIDهای OWUI را lookup نکند.
    """
    clean = dict(raw)
    gateway_files: list[dict] = []
    for item in raw.get("files") or []:
        if not isinstance(item, dict):
            continue
        if _is_openwebui_file_item(item):
            continue
        fid, name = _file_id_and_name(item)
        if fid:
            gateway_files.append({"id": fid, "name": name, "type": item.get("type")})
    clean["files"] = gateway_files
    return clean


def _last_user_text(messages: list[ChatMessage]) -> str:
    for m in reversed(messages):
        if m.role != "user":
            continue
        content = m.content
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for p in content:
                if isinstance(p, dict) and p.get("text"):
                    parts.append(str(p["text"]))
            return "\n".join(parts).strip()
        return str(content or "").strip()
    return ""


def _basename(name: str) -> str:
    from pathlib import PurePosixPath
    return PurePosixPath((name or "").strip()).name


def _inline_source_keys(text: str) -> set[str]:
    """نام/id منبع‌هایی که بدنهٔ معنادار inline دارند."""
    keys: set[str] = set()
    for sm in _SOURCE_RE.finditer(text or ""):
        attrs, body = sm.group(1), (sm.group(2) or "").strip()
        if len(body) < _MIN_INLINE_SOURCE_CHARS:
            continue
        if body.startswith("data:image"):
            continue
        name_m = re.search(r"""name=["']([^"']+)["']""", attrs, re.IGNORECASE)
        id_m = re.search(r"""id=["']([^"']+)["']""", attrs, re.IGNORECASE)
        if name_m:
            keys.add(_basename(name_m.group(1)))
        if id_m:
            keys.add(id_m.group(1).strip())
    return keys


def _ref_needs_fetch(fid: str, name: str, inline_keys: set[str]) -> bool:
    if fid in inline_keys:
        return False
    if name and name != fid and _basename(name) in inline_keys:
        return False
    return True


_ARABIC_PRESENTATION_RE = re.compile(r"[\uFB50-\uFDFF\uFE70-\uFEFF]")


def _normalize_document_text(text: str) -> str:
    """NFKC: حروف Presentation Form عربی/فارسی را به شکل استاندارد برمی‌گرداند."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    return normalized.strip()


def _normalize_sources_in_markup(text: str) -> str:
    """بدنهٔ داخل <source> را NFKC می‌کند (فیکس PDF فارسی OpenWebUI)."""

    def _repl(match: re.Match) -> str:
        attrs, body = match.group(1), match.group(2) or ""
        return f"<source{attrs}>{_normalize_document_text(body)}</source>"

    return _SOURCE_RE.sub(_repl, text or "")


def _is_pdf_filename(name: str) -> bool:
    return (name or "").lower().endswith(".pdf")


def _broken_arabic_pdf_text(text: str) -> bool:
    """متن استخراج‌شده با فونت‌های فارسی PDF اغلب به صورت حروف جدا (Presentation) می‌آید."""
    if not text or len(text) < 30:
        return True
    arabic = len(re.findall(r"[\u0600-\u06FF]", text))
    if arabic < 15:
        return False
    presentation = len(_ARABIC_PRESENTATION_RE.findall(text))
    if presentation / arabic > 0.25:
        return True
    # حروف فارسی با فاصله بین هر حرف: «ب ا ن ک»
    spaced = len(re.findall(r"[\u0600-\u06FF] ", text))
    return spaced / max(arabic, 1) > 0.15


def _extract_pdf_text_from_bytes(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages)


def _owui_auth_headers() -> tuple[str, dict[str, str]]:
    base = (settings.OPENWEBUI_BASE_URL or "").rstrip("/")
    token = (settings.OPENWEBUI_API_KEY or "").strip()
    if not base or not token:
        return "", {}
    return base, {"Authorization": f"Bearer {token}"}


async def fetch_openwebui_file_bytes(file_id: str) -> bytes:
    """دانلود فایل خام از OpenWebUI (/api/v1/files/{id}/content)."""
    base, headers = _owui_auth_headers()
    if not base:
        return b""

    url = f"{base}/api/v1/files/{file_id}/content"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.content or b""
    except Exception as exc:
        logger.warning("⚠️  OpenWebUI raw file fetch failed for %s: %s", file_id, exc)
        return b""


async def fetch_openwebui_file_text(file_id: str, *, filename: str = "") -> str:
    base, headers = _owui_auth_headers()
    if not base:
        return ""

    owui_text = ""
    url = f"{base}/api/v1/files/{file_id}/data/content"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            owui_text = (data.get("content", "") if isinstance(data, dict) else "") or ""
            owui_text = owui_text.strip()
    except Exception as exc:
        logger.warning("⚠️  OpenWebUI file content fetch failed for %s: %s", file_id, exc)

    is_pdf = _is_pdf_filename(filename) or owui_text.lstrip().startswith("%PDF")
    if not is_pdf:
        return _normalize_document_text(owui_text)

    normalized = _normalize_document_text(owui_text)
    if normalized and not _broken_arabic_pdf_text(normalized):
        return normalized

    raw = await fetch_openwebui_file_bytes(file_id)
    if not raw.startswith(b"%PDF"):
        return normalized

    try:
        pypdf_text = _normalize_document_text(_extract_pdf_text_from_bytes(raw))
    except Exception as exc:
        logger.warning("⚠️  pypdf extract failed for %s: %s", file_id, exc)
        return normalized

    if len(pypdf_text) > len(normalized):
        logger.info(
            "📄 PDF re-extracted via pypdf | file=%s | owui_chars=%d | pypdf_chars=%d",
            filename or file_id,
            len(normalized),
            len(pypdf_text),
        )
        if not _broken_arabic_pdf_text(pypdf_text):
            return pypdf_text
        # pypdf هم خراب است — همان خروجی بهتر را برگردان
        return pypdf_text if len(pypdf_text) >= len(normalized) else normalized

    return normalized or pypdf_text


def _inline_source_body(text: str, fid: str, name: str) -> str:
    """بدنهٔ <source> مربوط به یک فایل inline."""
    keys = {fid, _basename(name or "")}
    keys.discard("")
    for sm in _SOURCE_RE.finditer(text or ""):
        attrs, body = sm.group(1), (sm.group(2) or "").strip()
        name_m = re.search(r"""name=["']([^"']+)["']""", attrs, re.IGNORECASE)
        id_m = re.search(r"""id=["']([^"']+)["']""", attrs, re.IGNORECASE)
        matched = False
        if id_m and id_m.group(1).strip() in keys:
            matched = True
        if name_m and _basename(name_m.group(1)) in keys:
            matched = True
        if matched:
            return body
    return ""


def _refs_from_last_user_raw(raw: dict) -> list[tuple[str, str]]:
    for msg in reversed(raw.get("messages") or []):
        if isinstance(msg, dict) and msg.get("role") == "user":
            return _refs_from_message_files(msg.get("files"))
    return []


def _wrap_with_file_context(query: str, file_blocks: list[tuple[str, str]]) -> str:
    sources = "\n".join(
        f'<source id="{i + 1}" name="{name}">{text}</source>'
        for i, (name, text) in enumerate(file_blocks)
    )
    q = query or "Summarize the attached document."
    return (
        "### Task:\nRespond using the provided context.\n\n"
        f"<context>\n{sources}\n</context>\n\n"
        f"<user_query>\n{q}\n</user_query>\n"
    )


async def fetch_openwebui_chat(chat_id: str) -> dict | None:
    base = (settings.OPENWEBUI_BASE_URL or "").rstrip("/")
    token = (settings.OPENWEBUI_API_KEY or "").strip()
    if not base or not token or not chat_id:
        return None

    paths = (f"/api/v1/chats/{chat_id}", f"/api/chats/{chat_id}")
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        for path in paths:
            try:
                resp = await client.get(f"{base}{path}", headers=headers)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                data = resp.json()
                return data if isinstance(data, dict) else None
            except Exception as exc:
                logger.debug("OpenWebUI chat fetch %s failed: %s", path, exc)
    logger.warning("⚠️  Could not fetch OpenWebUI chat %s", chat_id)
    return None


def _ordered_messages_from_chat(chat_data: dict) -> list[dict]:
    chat = chat_data.get("chat") if isinstance(chat_data.get("chat"), dict) else chat_data
    history = chat.get("history") or {}
    messages_map = history.get("messages") or {}
    if messages_map:
        items = [m for m in messages_map.values() if isinstance(m, dict)]
        items.sort(key=lambda m: m.get("timestamp") or 0)
        return items
    msgs = chat.get("messages") or []
    return [m for m in msgs if isinstance(m, dict)]


def _refs_from_message_files(files: Any) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    seen: set[str] = set()
    if not isinstance(files, list):
        return refs
    for item in files:
        if not isinstance(item, dict):
            continue
        fid, name = _file_id_and_name(item)
        if fid and fid not in seen:
            seen.add(fid)
            refs.append((fid, name or fid))
    return refs


def extract_file_refs_from_chat(chat_data: dict) -> list[tuple[str, str]]:
    """همه فایل‌های پیام‌های user در chat OpenWebUI."""
    seen: set[str] = set()
    refs: list[tuple[str, str]] = []
    for msg in _ordered_messages_from_chat(chat_data):
        if msg.get("role") != "user":
            continue
        for fid, name in _refs_from_message_files(msg.get("files")):
            if fid not in seen:
                seen.add(fid)
                refs.append((fid, name))
    return refs


def _file_fp(name: str, fid: str) -> str:
    return name if name and name != fid else f"owui:{fid}"


def filter_new_chat_file_refs(
    chat_id: str,
    refs: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """فقط فایل‌هایی که هنوز در کش مکالمه دیده نشده‌اند."""
    key = f"id:{chat_id}"
    previous = get_seen_attachments(key) or set()
    out: list[tuple[str, str]] = []
    for fid, name in refs:
        if _file_fp(name, fid) not in previous and f"owui:{fid}" not in previous:
            out.append((fid, name))
    return out


def resolve_owui_chat_id(request_headers: dict, body: ChatCompletionRequest) -> str | None:
    for header in OWUI_CHAT_ID_HEADERS:
        value = request_headers.get(header)
        if value and str(value).strip():
            return str(value).strip()
    if body.conversation_id:
        return str(body.conversation_id)
    return None


async def resolve_openwebui_file_refs(
    raw: dict,
    chat_id: str | None,
) -> list[tuple[str, str]]:
    refs = extract_openwebui_file_refs(raw)
    if refs:
        return refs

    last_user_refs = _refs_from_last_user_raw(raw)
    if last_user_refs:
        return last_user_refs

    if not chat_id:
        return []

    chat_data = await fetch_openwebui_chat(chat_id)
    if not chat_data:
        return []

    chat_refs = extract_file_refs_from_chat(chat_data)
    new_refs = filter_new_chat_file_refs(chat_id, chat_refs)
    if new_refs:
        logger.info(
            "📂 OpenWebUI chat %s | total_files=%d | new_files=%s",
            chat_id,
            len(chat_refs),
            [r[0] for r in new_refs],
        )
        return new_refs

    if chat_refs:
        logger.info(
            "📂 OpenWebUI chat %s | files=%d but cache marked seen — re-fetch last user files",
            chat_id,
            len(chat_refs),
        )
        ordered = _ordered_messages_from_chat(chat_data)
        for msg in reversed(ordered):
            if msg.get("role") != "user":
                continue
            turn_refs = _refs_from_message_files(msg.get("files"))
            if turn_refs:
                return turn_refs
            break

    return []


async def fetch_image_base64_for_ocr(url: str) -> str:
    """واکشی تصویر از data-URL، HTTP یا OpenWebUI file id و برگرداندن base64 خام."""
    import base64

    u = (url or "").strip()
    if not u:
        return ""
    if u.startswith("owui-file://"):
        file_id = u[len("owui-file://"):]
        text = await fetch_openwebui_file_text(file_id)
        if not text:
            return ""
        if text.startswith("data:image") and "," in text:
            return text.split(",", 1)[1]
        return base64.b64encode(text.encode("utf-8")).decode("ascii")
    if u.startswith("data:image"):
        return u.split(",", 1)[1] if "," in u else ""

    if u.startswith("/"):
        base = (settings.OPENWEBUI_BASE_URL or "").rstrip("/")
        if base:
            u = f"{base}{u}"

    headers: dict[str, str] = {}
    token = (settings.OPENWEBUI_API_KEY or "").strip()
    if token and (settings.OPENWEBUI_BASE_URL or "") in u:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            resp = await client.get(u, headers=headers)
            resp.raise_for_status()
            raw = resp.content
            if not raw:
                return ""
            return base64.b64encode(raw).decode("ascii")
    except Exception as exc:
        logger.warning("⚠️  Image fetch for OCR failed (%s): %s", u[:80], exc)
        return ""


async def enrich_request_from_openwebui(
    raw: dict,
    body: ChatCompletionRequest,
    *,
    chat_id: str | None = None,
) -> ChatCompletionRequest:
    """
    اگر messages فایل ندارند، از payload خام یا chat OpenWebUI متن را می‌گیرد
    و به آخرین پیام user inject می‌کند.
    """
    if not settings.OPENWEBUI_FILE_FETCH_ENABLED:
        return body

    last_text = _last_user_text(body.messages)
    refs = await resolve_openwebui_file_refs(raw, chat_id)
    if not refs:
        if chat_id:
            logger.info(
                "📂 No OpenWebUI files for chat %s — check ENABLE_FORWARD_USER_INFO_HEADERS "
                "and OPENWEBUI_API_KEY in .env",
                chat_id,
            )
        return body

    inline_keys = _inline_source_keys(last_text)
    refs_to_fetch = [
        (fid, name) for fid, name in refs if _ref_needs_fetch(fid, name, inline_keys)
    ]
    if not refs_to_fetch:
        logger.info(
            "OpenWebUI file context already inline in message (%d source(s)); skip fetch",
            len(inline_keys),
        )
        messages = list(body.messages)
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].role != "user" or not isinstance(messages[i].content, str):
                continue
            content = messages[i].content
            normalized = _normalize_sources_in_markup(content)
            pdf_refs_to_reextract: list[tuple[str, str]] = []
            for fid, name in refs:
                if not _is_pdf_filename(name or ""):
                    continue
                inline_body = _inline_source_body(normalized, fid, name)
                if inline_body and _broken_arabic_pdf_text(inline_body):
                    pdf_refs_to_reextract.append((fid, name))

            if pdf_refs_to_reextract:
                file_blocks: list[tuple[str, str]] = []
                for fid, name in pdf_refs_to_reextract:
                    text = await fetch_openwebui_file_text(fid, filename=name)
                    if text:
                        file_blocks.append((name, text))
                        logger.info(
                            "📄 PDF inline broken; re-fetched %s (%s) | chars=%d",
                            name,
                            fid,
                            len(text),
                        )
                if file_blocks:
                    wrapped = _wrap_with_file_context(_last_user_text(messages), file_blocks)
                    messages[i] = messages[i].model_copy(update={"content": wrapped})
                    return body.model_copy(update={"messages": messages})

            if normalized != content:
                messages[i] = messages[i].model_copy(update={"content": normalized})
                return body.model_copy(update={"messages": messages})
            break
        return body

    file_blocks: list[tuple[str, str]] = []
    for fid, name in refs_to_fetch:
        text = await fetch_openwebui_file_text(fid, filename=name)
        if text:
            file_blocks.append((name, text))
            logger.info("📥 Fetched OpenWebUI file %s (%s) | chars=%d", name, fid, len(text))

    if not file_blocks:
        logger.warning(
            "⚠️  OpenWebUI file refs=%s but no content fetched — check OPENWEBUI_BASE_URL "
            "and OPENWEBUI_API_KEY in .env",
            [r[0] for r in refs],
        )
        return body

    wrapped = _wrap_with_file_context(last_text, file_blocks)
    messages = list(body.messages)
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].role == "user":
            messages[i] = messages[i].model_copy(update={"content": wrapped})
            break

    return body.model_copy(update={"messages": messages})


def log_incoming_payload_summary(raw: dict, *, chat_id: str | None = None) -> None:
    """خلاصه payload برای تشخیص اینکه OpenWebUI چه چیزی فوروارد کرده."""
    msgs = raw.get("messages") or []
    msg_lens = []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        c = m.get("content", "")
        if isinstance(c, str):
            msg_lens.append(len(c))
        elif isinstance(c, list):
            msg_lens.append(sum(len(str(p.get("text", ""))) for p in c if isinstance(p, dict)))
        else:
            msg_lens.append(0)

    refs = extract_openwebui_file_refs(raw)
    logger.info(
        "📨 OWUI→gateway | msgs=%d | msg_lens=%s | top_files=%d | owui_refs=%s | "
        "metadata_keys=%s | chat_id=%s",
        len(msgs),
        msg_lens,
        len(raw.get("files") or []),
        [r[0] for r in refs],
        list((raw.get("metadata") or {}).keys()) if isinstance(raw.get("metadata"), dict) else [],
        chat_id or "none",
    )
