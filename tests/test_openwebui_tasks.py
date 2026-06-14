from app.services.openwebui_tasks import (
    is_openwebui_internal_task,
    is_openwebui_internal_request,
    is_openwebui_internal_response,
    filter_openwebui_internal_history,
)


def test_detects_title_task():
    content = "### Task:\nGenerate a concise chat title for this conversation"
    assert is_openwebui_internal_task(content)


def test_detects_tags_task():
    content = "### Task:\nGenerate 1-3 broad tags categorizing the main themes"
    assert is_openwebui_internal_task(content)


def test_regular_message_is_not_internal():
    assert not is_openwebui_internal_task("Please write a function in Python")
    assert not is_openwebui_internal_task("")


def test_internal_request_checks_last_user_message():
    messages = [
        {"role": "system", "content": "you are helpful"},
        {"role": "user", "content": "### Task:\nGenerate a brief chat title"},
    ]
    assert is_openwebui_internal_request(messages)


def test_internal_response_json_detection():
    assert is_openwebui_internal_response('{"title": "Hello"}')
    assert not is_openwebui_internal_response("just a normal reply")


def test_filter_removes_internal_messages():
    class _Msg:
        def __init__(self, role, content):
            self.role = role
            self.content = content

    history = [
        _Msg("user", "real question"),
        _Msg("assistant", '{"tags": ["x"]}'),
        _Msg("assistant", "real answer"),
    ]
    filtered = filter_openwebui_internal_history(history)
    contents = [m.content for m in filtered]
    assert "real question" in contents
    assert "real answer" in contents
    assert '{"tags": ["x"]}' not in contents
