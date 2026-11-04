from app.services.search_v2 import chunk


def test_chunk_splits_long_text_on_sentences_and_keeps_all_words():
    text = " ".join(f"Sentence number {i} is here." for i in range(100))
    parts = chunk(text, limit=50)
    assert len(parts) > 1
    assert all(p.endswith(".") for p in parts)
    assert " ".join(parts) == text


def test_chunk_short_or_empty_text_returns_one_piece():
    assert chunk("Short answer.") == ["Short answer."]
    assert chunk("") == [""]
