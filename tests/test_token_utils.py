from app.services.token_utils import estimate_text_tokens, estimate_message_tokens


def test_empty_text_is_one_token():
    assert estimate_text_tokens("") == 1
    assert estimate_text_tokens("   ") == 1


def test_text_tokens_grow_with_length():
    short = estimate_text_tokens("hi")
    long = estimate_text_tokens("hello world this is a longer sentence")
    assert long > short


def test_long_word_splits_into_subtokens():
    assert estimate_text_tokens("a" * 20) > 1


def test_message_tokens_add_overhead():
    assert estimate_message_tokens({"content": "hi"}) >= estimate_text_tokens("hi")


def test_persian_text_counts():
    assert estimate_text_tokens("سلام دنیا") >= 2
