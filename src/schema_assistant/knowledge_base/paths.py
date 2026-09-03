from __future__ import annotations

import hashlib
import posixpath
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from schema_assistant.knowledge_base.models import ResourceKind

_SAFE_SEGMENT_RE = re.compile(r"[^a-z0-9._-]+")


def safe_segment(value: str) -> str:
    cleaned = _SAFE_SEGMENT_RE.sub("-", value.strip().lower()).strip(".-")
    if not cleaned:
        raise ValueError("path segment cannot be empty")
    return cleaned


def stable_hash(value: str, length: int = 24) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


class KnowledgeBasePathBuilder:
    def __init__(self, shard_count: int = 64) -> None:
        if shard_count <= 0:
            raise ValueError("shard_count must be positive")
        self._shard_count = shard_count

    def shard_for_source(self, source_uri: str) -> str:
        shard_number = int(stable_hash(source_uri, length=8), 16) % self._shard_count
        return f"s{shard_number:03d}"

    def chunk_id(self, source_uri: str, chunk_index: int, content: str) -> str:
        if chunk_index < 0:
            raise ValueError("chunk_index cannot be negative")
        return stable_hash(f"{source_uri}:{chunk_index}:{content}", length=32)

    def firestore_chunk_path(
        self,
        entity_id: str,
        resource_id: ResourceKind,
        shard_id: str,
        chunk_id: str,
    ) -> str:
        return "/".join(
            [
                "entities",
                safe_segment(entity_id),
                "resources",
                safe_segment(resource_id),
                "shards",
                safe_segment(shard_id),
                "chunks",
                safe_segment(chunk_id),
            ]
        )

    def github_raw_object_path(
        self,
        entity_id: str,
        resource_id: ResourceKind,
        source_hash: str,
        relative_path: str,
    ) -> str:
        return _join_storage_path(
            "raw",
            "github",
            safe_segment(entity_id),
            safe_segment(resource_id),
            safe_segment(source_hash),
            relative_path,
        )

    def processed_object_path(
        self,
        entity_id: str,
        resource_id: ResourceKind,
        source_hash: str,
    ) -> str:
        return _join_storage_path(
            "processed",
            safe_segment(entity_id),
            safe_segment(resource_id),
            f"{safe_segment(source_hash)}.json",
        )

    def docs_object_path(self, filename: str) -> str:
        return _join_storage_path("raw", "docs", filename)


def _join_storage_path(*parts: str) -> str:
    normalized = []
    for part in parts:
        cleaned = part.replace("\\", "/").strip("/")
        if not cleaned or cleaned == "." or ".." in cleaned.split("/"):
            raise ValueError("storage path contains an unsafe segment")
        normalized.append(cleaned)
    return posixpath.join(*normalized)
