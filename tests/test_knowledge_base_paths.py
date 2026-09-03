from schema_assistant.knowledge_base.paths import KnowledgeBasePathBuilder, safe_segment


def test_firestore_path_uses_entity_resource_shard_and_chunks() -> None:
    paths = KnowledgeBasePathBuilder(shard_count=8)
    shard_id = paths.shard_for_source("https://github.com/istat/example.ttl")
    chunk_id = paths.chunk_id("https://github.com/istat/example.ttl", 0, "contenuto")

    assert paths.firestore_chunk_path("ISTAT", "ontologies", shard_id, chunk_id) == (
        f"entities/istat/resources/ontologies/shards/{shard_id}/chunks/{chunk_id}"
    )


def test_storage_paths_reject_parent_segments() -> None:
    paths = KnowledgeBasePathBuilder()

    try:
        paths.docs_object_path("../secret.txt")
    except ValueError as exc:
        assert "unsafe" in str(exc)
    else:
        raise AssertionError("unsafe storage path was accepted")


def test_safe_segment_normalizes_readable_ids() -> None:
    assert safe_segment("  YAML Schemas  ") == "yaml-schemas"
