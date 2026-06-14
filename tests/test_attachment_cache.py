from app.core.attachment_cache import (
    bootstrap_seen_attachments,
    delete_seen_attachments,
    get_seen_attachments,
    reset_memory_fallback,
    set_seen_attachments,
)


_TEST_KEYS = ("conv:test-1", "conv:test-2", "conv:test-3", "conv:test-4")


def setup_function():
    reset_memory_fallback()
    for key in _TEST_KEYS:
        delete_seen_attachments(key)


def test_get_seen_returns_none_when_missing():
    assert get_seen_attachments("conv:test-1") is None


def test_set_and_get_seen_attachments_memory_fallback():
    key = "conv:test-2"
    set_seen_attachments(key, {"file_a.txt", "img:abc"})
    seen = get_seen_attachments(key)
    assert seen == {"file_a.txt", "img:abc"}


def test_bootstrap_only_sets_when_missing():
    key = "conv:test-3"
    bootstrap_seen_attachments(key, {"seed.txt"})
    assert get_seen_attachments(key) == {"seed.txt"}
    set_seen_attachments(key, {"seed.txt", "new.pdf"})
    bootstrap_seen_attachments(key, {"other.txt"})
    assert get_seen_attachments(key) == {"seed.txt", "new.pdf"}


def test_delete_seen_attachments():
    key = "conv:test-4"
    set_seen_attachments(key, {"x.txt"})
    delete_seen_attachments(key)
    assert get_seen_attachments(key) is None
