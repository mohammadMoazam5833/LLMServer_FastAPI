from app.core.security import (
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)


def test_generate_api_key_has_prefix():
    key = generate_api_key()
    assert key.startswith("sk-")
    assert len(key) > 10


def test_hash_api_key_is_deterministic_sha256():
    h1 = hash_api_key("some-key")
    h2 = hash_api_key("some-key")
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex digest
    assert hash_api_key("other") != h1


def test_password_roundtrip():
    hashed = hash_password("s3cret-pass")
    assert hashed != "s3cret-pass"
    assert verify_password("s3cret-pass", hashed)
    assert not verify_password("wrong", hashed)


def test_verify_password_handles_bad_hash():
    assert not verify_password("anything", "not-a-valid-hash")
