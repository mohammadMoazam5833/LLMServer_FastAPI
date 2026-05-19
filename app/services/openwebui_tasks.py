from __future__ import annotations

import json
from typing import Any


OPENWEBUI_TASK_PREFIX = "### Task:"
OPENWEBUI_INTERNAL_TASK_MARKERS = (
    "Generate 1-3 broad tags categorizing",
    "Suggest 3-5 relevant follow-up questions",
    "Generate a concise",
    "Generate a brief",
    "Generate a short",
    "chat title",
    "conversation title",
)
OPENWEBUI_INTERNAL_RESPONSE_KEYS = (
    "tags",
    "subtopics",
    "subtopic_tags",
    "follow_ups",
    "follow-up",
    "title",
)


def _message_role(message: Any) -> str:
    return message.role if hasattr(message, "role") else message.get("role", "")


def _message_content(message: Any) -> str:
    return message.content if hasattr(message, "content") else message.get("content", "")


def is_openwebui_internal_task(content: str) -> bool:
    if not content:
        return False

    normalized = content.strip()
    return normalized.startswith(OPENWEBUI_TASK_PREFIX) and any(
        marker in normalized for marker in OPENWEBUI_INTERNAL_TASK_MARKERS
    )


def is_openwebui_internal_request(messages: list[Any]) -> bool:
    for message in reversed(messages):
        if _message_role(message) == "user":
            return is_openwebui_internal_task(_message_content(message))
    return False


def is_openwebui_internal_response(content: str) -> bool:
    normalized = (content or "").strip().strip("`")
    if not normalized.startswith("{"):
        return False

    try:
        data = json.loads(normalized)
    except json.JSONDecodeError:
        return any(key in normalized for key in OPENWEBUI_INTERNAL_RESPONSE_KEYS)

    return any(key in data for key in OPENWEBUI_INTERNAL_RESPONSE_KEYS)


def is_openwebui_internal_content(content: str) -> bool:
    return is_openwebui_internal_task(content) or is_openwebui_internal_response(content)


def filter_openwebui_internal_history(history: list[Any]) -> list[Any]:
    return [
        message
        for message in history
        if not is_openwebui_internal_content(_message_content(message))
    ]
