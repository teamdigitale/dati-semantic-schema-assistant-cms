from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from schema_assistant.agent.logging import configure_logging
from schema_assistant.ingestion.chunking import chunk_text
from schema_assistant.ingestion.config import IngestionSettings, get_settings
from schema_assistant.ingestion.discovery import (
    SourceFile,
    discover_entity_files,
    discover_local_docs,
    discover_storage_docs,
)
from schema_assistant.ingestion.entities import EntityConfig, load_entities_config
from schema_assistant.ingestion.github import clone_repository, resolve_assets_dir
from schema_assistant.ingestion.parsers import AssetParser, ParsedAsset
from schema_assistant.ingestion.report import IngestionReport
from schema_assistant.knowledge_base.embeddings import VertexEmbeddingClient
from schema_assistant.knowledge_base.firestore_store import FirestoreVectorStore
from schema_assistant.knowledge_base.models import (
    AssetMetadataDocument,
    ChunkDocument,
    SourceDocument,
)
from schema_assistant.knowledge_base.paths import (
    KnowledgeBasePathBuilder,
    safe_segment,
    stable_hash,
)
from schema_assistant.knowledge_base.storage import ObjectStorage

logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    configure_logging("INFO")
    report = run_ingestion(settings)
    print(report.model_dump_json(indent=2))

    if report.files_failed > 0:
        raise SystemExit(1)


def run_ingestion(settings: IngestionSettings) -> IngestionReport:
    _validate_settings(settings)

    report = IngestionReport(dry_run=settings.dry_run)
    entities = load_entities_config(settings.entities_config_path)
    report.entities_seen = len(entities)

    storage = ObjectStorage(settings.bucket_name, project_id=settings.project_id)
    paths = KnowledgeBasePathBuilder()
    parser = AssetParser(max_triples_per_file=settings.max_triples_per_file)
    embeddings = VertexEmbeddingClient(
        project_id=settings.project_id,
        location=settings.location,
        model=settings.embedding_model,
        output_dimensionality=settings.embedding_dimension,
        batch_size=settings.embedding_batch_size,
    )
    vector_store = FirestoreVectorStore(
        project_id=settings.project_id,
        database=settings.firestore_database,
        chunks_collection_group=settings.chunks_collection_group,
        write_batch_size=settings.firestore_write_batch_size,
    )

    with tempfile.TemporaryDirectory(prefix="schema-assistant-ingestion-") as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        sources = _collect_sources(entities, settings, storage, tmp_dir)
        report.files_seen = len(sources)

        for source in sources:
            try:
                _process_source(
                    source=source,
                    settings=settings,
                    storage=storage,
                    paths=paths,
                    parser=parser,
                    embeddings=embeddings,
                    vector_store=vector_store,
                    report=report,
                )
            except Exception as exc:
                logger.exception("ingestion_source_failed", extra={"source_uri": source.source_uri})
                report.mark_failure(source_uri=source.source_uri, error=str(exc))

    report.finish()
    _write_report(settings, storage, report)
    return report


def _collect_sources(
    entities: list[EntityConfig],
    settings: IngestionSettings,
    storage: ObjectStorage,
    tmp_dir: Path,
) -> list[SourceFile]:
    sources: list[SourceFile] = []

    for entity in entities:
        repo_dir = tmp_dir / "repos" / safe_segment(entity.name)
        logger.info(
            "clone_repository", extra={"entity_id": entity.name, "repo_url": str(entity.repo_url)}
        )
        clone_repository(str(entity.repo_url), repo_dir)
        assets_dir = resolve_assets_dir(repo_dir, entity.assets_path)
        sources.extend(discover_entity_files(entity, repo_dir, assets_dir))

    if settings.local_docs_dir:
        sources.extend(discover_local_docs(settings.local_docs_dir))

    if settings.gcs_docs_prefix:
        sources.extend(
            discover_storage_docs(
                storage,
                settings.gcs_docs_prefix,
                tmp_dir / "storage-docs",
            )
        )

    return sources


def _process_source(
    *,
    source: SourceFile,
    settings: IngestionSettings,
    storage: ObjectStorage,
    paths: KnowledgeBasePathBuilder,
    parser: AssetParser,
    embeddings: VertexEmbeddingClient,
    vector_store: FirestoreVectorStore,
    report: IngestionReport,
) -> None:
    parsed = parser.parse(source)
    if parsed.content_type == "application/pdf":
        total_pages = int(parsed.processed_payload.get("page_count") or 0)
        text_pages = int(parsed.processed_payload.get("text_page_count") or 0)
        if text_pages < total_pages:
            logger.warning(
                "ingestion_pdf_partial_text",
                extra={
                    "source_uri": source.source_uri,
                    "total_pages": total_pages,
                    "text_pages": text_pages,
                },
            )
    raw_storage_uri = _upload_raw_asset(storage, paths, parsed, settings.dry_run)
    processed_storage_uri = _upload_processed_asset(storage, paths, parsed, settings.dry_run)
    chunks = chunk_text(
        parsed.content,
        max_chars=settings.max_chunk_chars,
        overlap_chars=settings.chunk_overlap_chars,
    )

    if not chunks:
        logger.warning("ingestion_source_empty", extra={"source_uri": source.source_uri})
        report.mark_file(
            entity_id=source.entity_id,
            resource_id=source.resource_id,
            chunks=0,
            raw_written=bool(raw_storage_uri) and not bool(source.origin_storage_uri),
            processed_written=bool(processed_storage_uri),
        )
        return

    source_document = SourceDocument(
        entity_id=source.entity_id,
        resource_id=source.resource_id,
        source_uri=source.source_uri,
        storage_uri=raw_storage_uri,
        source_hash=parsed.source_hash,
        content_type=parsed.content_type,
        metadata={
            "relative_path": source.relative_path,
            "repo_url": source.repo_url,
            "processed_storage_uri": processed_storage_uri,
        },
    )
    asset_document = _asset_metadata_document(
        parsed=parsed,
        raw_storage_uri=raw_storage_uri,
        processed_storage_uri=processed_storage_uri,
    )
    source_uri_hash = stable_hash(source.source_uri, length=32)

    if not settings.dry_run:
        existing_source = vector_store.get_source_index(
            entity_id=source.entity_id,
            resource_id=source.resource_id,
            source_uri_hash=source_uri_hash,
        )
        vector_store.upsert_source(source_document)
        vector_store.upsert_asset_metadata(
            asset_document,
            source_uri_hash=source_uri_hash,
        )
        if (
            existing_source
            and existing_source.source_hash == parsed.source_hash
            and existing_source.status == "completed"
        ):
            report.mark_skipped(
                entity_id=source.entity_id,
                resource_id=source.resource_id,
                chunks=existing_source.chunks_written,
            )
            logger.info(
                "ingestion_source_skipped",
                extra={
                    "entity_id": source.entity_id,
                    "resource_id": source.resource_id,
                    "source_uri": source.source_uri,
                    "source_hash": parsed.source_hash,
                },
            )
            return

        vector_store.mark_source_processing(
            source=source_document,
            source_uri_hash=source_uri_hash,
        )
        vector_store.delete_chunks_for_source(
            entity_id=source.entity_id,
            resource_id=source.resource_id,
            shard_id=paths.shard_for_source(source.source_uri),
            source_uri=source.source_uri,
        )
        written = _embed_and_write_chunks(
            source=source,
            parsed=parsed,
            chunks=chunks,
            storage_uri=processed_storage_uri,
            paths=paths,
            embeddings=embeddings,
            vector_store=vector_store,
            batch_size=settings.firestore_write_batch_size,
            dry_run=False,
        )
        vector_store.mark_source_completed(
            source=source_document,
            source_uri_hash=source_uri_hash,
            chunks_written=written,
        )
    else:
        written = _embed_and_write_chunks(
            source=source,
            parsed=parsed,
            chunks=chunks,
            storage_uri=processed_storage_uri,
            paths=paths,
            embeddings=embeddings,
            vector_store=vector_store,
            batch_size=settings.firestore_write_batch_size,
            dry_run=True,
        )

    report.mark_file(
        entity_id=source.entity_id,
        resource_id=source.resource_id,
        chunks=written,
        raw_written=bool(raw_storage_uri) and not bool(source.origin_storage_uri),
        processed_written=bool(processed_storage_uri),
    )
    logger.info(
        "ingestion_source_completed",
        extra={
            "entity_id": source.entity_id,
            "resource_id": source.resource_id,
            "source_uri": source.source_uri,
            "chunks": written,
        },
    )


def _embed_and_write_chunks(
    *,
    source: SourceFile,
    parsed: ParsedAsset,
    chunks: list[str],
    storage_uri: str | None,
    paths: KnowledgeBasePathBuilder,
    embeddings: VertexEmbeddingClient,
    vector_store: FirestoreVectorStore,
    batch_size: int,
    dry_run: bool,
) -> int:
    written = 0
    for start_index in range(0, len(chunks), batch_size):
        chunk_batch = chunks[start_index : start_index + batch_size]
        vectors = (
            _dry_run_vectors(chunk_batch) if dry_run else embeddings.embed_documents(chunk_batch)
        )
        chunk_documents = [
            _chunk_document(
                source=source,
                parsed=parsed,
                content=content,
                embedding=embedding,
                chunk_index=start_index + offset,
                storage_uri=storage_uri,
                paths=paths,
            )
            for offset, (content, embedding) in enumerate(zip(chunk_batch, vectors, strict=True))
        ]

        written += len(chunk_documents) if dry_run else vector_store.upsert_chunks(chunk_documents)
        logger.info(
            "ingestion_chunks_batch_completed",
            extra={
                "source_uri": source.source_uri,
                "chunk_start": start_index,
                "chunk_count": len(chunk_documents),
                "total_chunks": len(chunks),
            },
        )
    return written


def _upload_raw_asset(
    storage: ObjectStorage,
    paths: KnowledgeBasePathBuilder,
    parsed: ParsedAsset,
    dry_run: bool,
) -> str | None:
    source = parsed.source
    if source.origin_storage_uri:
        return source.origin_storage_uri
    if source.repo_url:
        object_path = paths.github_raw_object_path(
            source.entity_id,
            source.resource_id,
            parsed.source_hash,
            source.relative_path,
        )
    else:
        object_path = paths.docs_object_path(f"{parsed.source_hash}/{source.relative_path}")
    if dry_run:
        return storage.uri_for(object_path)

    return storage.upload_bytes(
        object_path,
        source.path.read_bytes(),
        content_type=parsed.content_type,
        metadata=_storage_metadata(parsed),
    )


def _upload_processed_asset(
    storage: ObjectStorage,
    paths: KnowledgeBasePathBuilder,
    parsed: ParsedAsset,
    dry_run: bool,
) -> str | None:
    object_path = paths.processed_object_path(
        parsed.source.entity_id,
        parsed.source.resource_id,
        parsed.source_hash,
    )
    if dry_run:
        return storage.uri_for(object_path)

    return storage.upload_text(
        object_path,
        json.dumps(parsed.processed_payload, ensure_ascii=False, indent=2, default=str),
        content_type="application/json; charset=utf-8",
        metadata=_storage_metadata(parsed),
    )


def _chunk_document(
    *,
    source: SourceFile,
    parsed: ParsedAsset,
    content: str,
    embedding: list[float],
    chunk_index: int,
    storage_uri: str | None,
    paths: KnowledgeBasePathBuilder,
) -> ChunkDocument:
    shard_id = paths.shard_for_source(source.source_uri)
    chunk_id = paths.chunk_id(source.source_uri, chunk_index, content)
    return ChunkDocument(
        chunk_id=chunk_id,
        entity_id=source.entity_id,
        resource_id=source.resource_id,
        shard_id=shard_id,
        content=content,
        embedding=embedding,
        source_uri=source.source_uri,
        storage_uri=storage_uri,
        source_hash=parsed.source_hash,
        chunk_index=chunk_index,
        token_count=max(1, len(content) // 4),
        metadata={
            "relative_path": source.relative_path,
            "content_type": parsed.content_type,
        },
    )


def _asset_metadata_document(
    *,
    parsed: ParsedAsset,
    raw_storage_uri: str | None,
    processed_storage_uri: str | None,
) -> AssetMetadataDocument:
    source = parsed.source
    payload = parsed.processed_payload
    labels = _string_list(payload.get("asset_labels"))
    keywords = _string_list(payload.get("asset_keywords"))
    title = _asset_title(source.relative_path, labels)

    return AssetMetadataDocument(
        entity_id=source.entity_id,
        resource_id=source.resource_id,
        source_uri=source.source_uri,
        source_hash=parsed.source_hash,
        title=title,
        relative_path=source.relative_path,
        repo_url=source.repo_url,
        storage_uri=raw_storage_uri,
        processed_storage_uri=processed_storage_uri,
        content_type=parsed.content_type,
        format=str(payload.get("format") or source.path.suffix.lstrip(".") or "text"),
        labels=labels[:80],
        keywords=_dedupe_text([*keywords, *_path_keywords(source.relative_path)], limit=140),
        metadata={
            "triple_count": payload.get("triple_count"),
            "subject_count": payload.get("subject_count"),
            "row_count": payload.get("row_count"),
            "page_count": payload.get("page_count"),
            "text_page_count": payload.get("text_page_count"),
            "extracted_chars": payload.get("extracted_chars"),
        },
    )


def _asset_title(relative_path: str, labels: list[str]) -> str:
    if labels:
        return labels[0]

    filename = Path(relative_path).stem
    return filename.replace("_", " ").replace("-", " ").strip() or relative_path


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _path_keywords(relative_path: str) -> list[str]:
    normalized = relative_path.replace("/", " ").replace("_", " ").replace("-", " ")
    return [token.lower() for token in normalized.split() if len(token) >= 3]


def _dedupe_text(items: list[str], *, limit: int) -> list[str]:
    deduped = []
    seen = set()
    for item in items:
        text = str(item).strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        deduped.append(text)
        if len(deduped) >= limit:
            break
    return deduped


def _write_report(
    settings: IngestionSettings,
    storage: ObjectStorage,
    report: IngestionReport,
) -> None:
    report_payload = report.model_dump(mode="json")
    object_name = _report_object_name(report_payload)
    if settings.dry_run:
        logger.info("ingestion_report_dry_run", extra={"object_path": object_name})
        return

    storage.upload_text(
        object_name,
        json.dumps(report_payload, ensure_ascii=False, indent=2, default=str),
        content_type="application/json; charset=utf-8",
        metadata={"app": "schema-assistant", "kind": "ingestion-report"},
    )


def _report_object_name(report_payload: dict[str, Any]) -> str:
    started_at = str(report_payload["started_at"]).replace(":", "").replace("+", "Z")
    return f"reports/ingestion/{started_at}.json"


def _storage_metadata(parsed: ParsedAsset) -> dict[str, str]:
    return {
        "entity_id": parsed.source.entity_id,
        "resource_id": parsed.source.resource_id,
        "source_hash": parsed.source_hash,
    }


def _dry_run_vectors(chunks: list[str]) -> list[list[float]]:
    return [[0.0, 1.0] for _ in chunks]


def _validate_settings(settings: IngestionSettings) -> None:
    if not settings.project_id:
        raise ValueError("GOOGLE_CLOUD_PROJECT is required")
    if not settings.bucket_name:
        raise ValueError("SCHEMA_ASSISTANT_BUCKET is required")
    if settings.chunk_overlap_chars >= settings.max_chunk_chars:
        raise ValueError("INGESTION_CHUNK_OVERLAP_CHARS must be lower than max chunk chars")
    if not settings.entities_config_path.exists():
        raise FileNotFoundError(f"Entities config not found: {settings.entities_config_path}")
