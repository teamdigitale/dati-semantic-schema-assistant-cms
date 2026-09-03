from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, cast

from google.cloud import firestore
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector

from schema_assistant.knowledge_base.models import (
    AssetMetadataDocument,
    ChunkDocument,
    MetadataSearchResult,
    SearchResult,
    SourceDocument,
)

CHUNKS_COLLECTION_GROUP = "chunks"
EMBEDDING_FIELD = "embedding"
DISTANCE_FIELD = "vector_distance"


@dataclass(frozen=True)
class SourceIndexEntry:
    source_uri: str
    source_hash: str
    status: str
    chunks_written: int


class FirestoreVectorStore:
    def __init__(
        self,
        *,
        project_id: str,
        database: str = "(default)",
        chunks_collection_group: str = CHUNKS_COLLECTION_GROUP,
        write_batch_size: int = 50,
    ) -> None:
        if not project_id:
            raise ValueError("project_id is required")
        if write_batch_size <= 0 or write_batch_size > 450:
            raise ValueError("write_batch_size must be between 1 and 450")

        self._client = firestore.Client(project=project_id, database=database)
        self._chunks_collection_group = chunks_collection_group
        self._write_batch_size = write_batch_size

    def get_source_index(
        self,
        *,
        entity_id: str,
        resource_id: str,
        source_uri_hash: str,
    ) -> SourceIndexEntry | None:
        snapshot = self._source_index_ref(
            entity_id=entity_id,
            resource_id=resource_id,
            source_uri_hash=source_uri_hash,
        ).get()
        if not snapshot.exists:
            return None

        data = snapshot.to_dict() or {}
        return SourceIndexEntry(
            source_uri=str(data.get("source_uri", "")),
            source_hash=str(data.get("source_hash", "")),
            status=str(data.get("status", "")),
            chunks_written=int(data.get("chunks_written") or 0),
        )

    def mark_source_processing(
        self,
        *,
        source: SourceDocument,
        source_uri_hash: str,
    ) -> None:
        self._source_index_ref(
            entity_id=source.entity_id,
            resource_id=source.resource_id,
            source_uri_hash=source_uri_hash,
        ).set(
            {
                "source_uri": source.source_uri,
                "source_hash": source.source_hash,
                "status": "processing",
                "started_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )

    def mark_source_completed(
        self,
        *,
        source: SourceDocument,
        source_uri_hash: str,
        chunks_written: int,
    ) -> None:
        self._source_index_ref(
            entity_id=source.entity_id,
            resource_id=source.resource_id,
            source_uri_hash=source_uri_hash,
        ).set(
            {
                "source_uri": source.source_uri,
                "source_hash": source.source_hash,
                "status": "completed",
                "chunks_written": chunks_written,
                "completed_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )

    def upsert_source(self, source: SourceDocument) -> None:
        entity_ref = self._client.collection("entities").document(source.entity_id)
        resource_ref = entity_ref.collection("resources").document(source.resource_id)
        source_ref = resource_ref.collection("sources").document(source.source_hash)

        batch = self._client.batch()
        batch.set(
            entity_ref,
            {
                "entity_id": source.entity_id,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
        batch.set(
            resource_ref,
            {
                "entity_id": source.entity_id,
                "resource_id": source.resource_id,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
        batch.set(
            source_ref,
            {
                **source.model_dump(mode="json"),
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
        batch.commit()

    def upsert_asset_metadata(
        self,
        asset: AssetMetadataDocument,
        *,
        source_uri_hash: str,
    ) -> None:
        entity_ref = self._client.collection("entities").document(asset.entity_id)
        resource_ref = entity_ref.collection("resources").document(asset.resource_id)
        asset_ref = resource_ref.collection("asset_index").document(source_uri_hash)

        batch = self._client.batch()
        batch.set(
            entity_ref,
            {
                "entity_id": asset.entity_id,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
        batch.set(
            resource_ref,
            {
                "entity_id": asset.entity_id,
                "resource_id": asset.resource_id,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
        batch.set(
            asset_ref,
            {
                **asset.model_dump(mode="json"),
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
        batch.commit()

    def list_asset_metadata(
        self,
        *,
        entity_ids: set[str],
        resource_ids: set[str],
        limit_per_resource: int = 200,
    ) -> list[MetadataSearchResult]:
        if not entity_ids or not resource_ids:
            return []
        if limit_per_resource <= 0:
            raise ValueError("limit_per_resource must be positive")

        results: list[MetadataSearchResult] = []
        for entity_id in sorted(entity_ids):
            for resource_id in sorted(resource_ids):
                collection = (
                    self._client.collection("entities")
                    .document(entity_id)
                    .collection("resources")
                    .document(resource_id)
                    .collection("asset_index")
                )
                for snapshot in collection.limit(limit_per_resource).stream():
                    data = snapshot.to_dict() or {}
                    results.append(_metadata_result(data))
        return results

    def upsert_chunks(self, chunks: Sequence[ChunkDocument]) -> int:
        written = 0
        for chunk_batch in _batches(chunks, self._write_batch_size):
            batch = self._client.batch()
            for chunk in chunk_batch:
                ref = self._chunk_ref(chunk)
                payload = _chunk_payload(chunk)
                batch.set(ref, payload, merge=True)
                written += 1
            batch.commit()
        return written

    def delete_chunks_for_source(
        self,
        *,
        entity_id: str,
        resource_id: str,
        shard_id: str,
        source_uri: str,
    ) -> int:
        collection = (
            self._client.collection("entities")
            .document(entity_id)
            .collection("resources")
            .document(resource_id)
            .collection("shards")
            .document(shard_id)
            .collection(self._chunks_collection_group)
        )

        deleted = 0
        batch = self._client.batch()
        batch_size = 0
        for snapshot in collection.where("source_uri", "==", source_uri).stream():
            batch.delete(snapshot.reference)
            deleted += 1
            batch_size += 1
            if batch_size >= 450:
                batch.commit()
                batch = self._client.batch()
                batch_size = 0

        if batch_size:
            batch.commit()
        return deleted

    def search(
        self,
        query_vector: Sequence[float],
        *,
        limit: int = 8,
        entity_ids: set[str] | None = None,
        resource_ids: set[str] | None = None,
    ) -> list[SearchResult]:
        if limit <= 0:
            raise ValueError("limit must be positive")

        scopes = _search_scopes(entity_ids, resource_ids)
        results: list[SearchResult] = []
        for entity_id, resource_id in scopes:
            query = self._client.collection_group(self._chunks_collection_group)
            if entity_id:
                query = query.where("entity_id", "==", entity_id)
            if resource_id:
                query = query.where("resource_id", "==", resource_id)

            vector_query = query.find_nearest(
                vector_field=EMBEDDING_FIELD,
                query_vector=Vector(list(query_vector)),
                distance_measure=DistanceMeasure.COSINE,
                limit=limit,
                distance_result_field=DISTANCE_FIELD,
            )
            for snapshot in vector_query.stream():
                results.append(_search_result(snapshot.id, snapshot.to_dict() or {}))

        return _rank_search_results(results, limit=limit)

    def _chunk_ref(self, chunk: ChunkDocument) -> Any:
        return (
            self._client.collection("entities")
            .document(chunk.entity_id)
            .collection("resources")
            .document(chunk.resource_id)
            .collection("shards")
            .document(chunk.shard_id)
            .collection(self._chunks_collection_group)
            .document(chunk.chunk_id)
        )

    def _source_index_ref(
        self,
        *,
        entity_id: str,
        resource_id: str,
        source_uri_hash: str,
    ) -> Any:
        return (
            self._client.collection("entities")
            .document(entity_id)
            .collection("resources")
            .document(resource_id)
            .collection("source_index")
            .document(source_uri_hash)
        )


def _chunk_payload(chunk: ChunkDocument) -> dict[str, Any]:
    payload = cast(
        dict[str, Any], chunk.model_dump(mode="json", exclude={"created_at", "updated_at"})
    )
    payload[EMBEDDING_FIELD] = Vector(chunk.embedding)
    payload["created_at"] = chunk.created_at or firestore.SERVER_TIMESTAMP
    payload["updated_at"] = firestore.SERVER_TIMESTAMP
    return payload


def _search_result(snapshot_id: str, data: dict[str, Any]) -> SearchResult:
    return SearchResult(
        chunk_id=str(data.get("chunk_id") or snapshot_id),
        entity_id=str(data["entity_id"]),
        resource_id=data["resource_id"],
        content=str(data["content"]),
        source_uri=str(data["source_uri"]),
        storage_uri=data.get("storage_uri"),
        distance=data.get(DISTANCE_FIELD),
        metadata=data.get("metadata") or {},
    )


def _search_scopes(
    entity_ids: set[str] | None,
    resource_ids: set[str] | None,
) -> list[tuple[str | None, str | None]]:
    entities = sorted(entity_ids) if entity_ids else [None]
    resources = sorted(resource_ids) if resource_ids else [None]
    return [(entity_id, resource_id) for entity_id in entities for resource_id in resources]


def _rank_search_results(results: list[SearchResult], *, limit: int) -> list[SearchResult]:
    deduplicated: dict[str, SearchResult] = {}
    for result in results:
        existing = deduplicated.get(result.chunk_id)
        if existing is None or _distance(result) < _distance(existing):
            deduplicated[result.chunk_id] = result
    return sorted(deduplicated.values(), key=_distance)[:limit]


def _distance(result: SearchResult) -> float:
    return result.distance if result.distance is not None else float("inf")


def _metadata_result(data: dict[str, Any]) -> MetadataSearchResult:
    return MetadataSearchResult(
        entity_id=str(data["entity_id"]),
        resource_id=data["resource_id"],
        source_uri=str(data["source_uri"]),
        source_hash=str(data["source_hash"]),
        title=str(data["title"]),
        relative_path=str(data["relative_path"]),
        labels=[str(item) for item in data.get("labels") or []],
        keywords=[str(item) for item in data.get("keywords") or []],
        content_type=str(data.get("content_type") or "text/plain"),
        format=data.get("format"),
        metadata=data.get("metadata") or {},
    )


def _batches(items: Sequence[ChunkDocument], size: int) -> Iterable[Sequence[ChunkDocument]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]
