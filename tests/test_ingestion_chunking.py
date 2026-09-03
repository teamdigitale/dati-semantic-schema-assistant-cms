from schema_assistant.ingestion.chunking import chunk_text


def test_chunk_text_keeps_small_content_together() -> None:
    chunks = chunk_text("prima parte\n\nseconda parte", max_chars=100, overlap_chars=10)

    assert chunks == ["prima parte\n\nseconda parte"]


def test_chunk_text_splits_with_overlap() -> None:
    text = "a" * 50 + "\n\n" + "b" * 50

    chunks = chunk_text(text, max_chars=60, overlap_chars=5)

    assert len(chunks) == 2
    assert chunks[1].startswith("aaaaa")


def test_chunk_text_prefers_readable_boundaries() -> None:
    text = "Prima frase completa. Seconda frase completa. Terza frase molto lunga."

    chunks = chunk_text(text, max_chars=45, overlap_chars=5)

    assert chunks[0].endswith(".")
    assert all(len(chunk) <= 45 for chunk in chunks)
