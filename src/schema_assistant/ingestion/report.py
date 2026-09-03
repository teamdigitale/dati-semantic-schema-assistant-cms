from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IngestionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    dry_run: bool = False
    entities_seen: int = 0
    files_seen: int = 0
    files_processed: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    chunks_written: int = 0
    raw_objects_written: int = 0
    processed_objects_written: int = 0
    failures: list[dict[str, Any]] = Field(default_factory=list)
    by_entity: dict[str, dict[str, int]] = Field(default_factory=dict)

    def mark_file(
        self,
        *,
        entity_id: str,
        resource_id: str,
        chunks: int,
        raw_written: bool,
        processed_written: bool,
    ) -> None:
        self.files_processed += 1
        self.chunks_written += chunks
        self.raw_objects_written += int(raw_written)
        self.processed_objects_written += int(processed_written)

        entity_stats = self.by_entity.setdefault(entity_id, {})
        entity_stats["files"] = entity_stats.get("files", 0) + 1
        entity_stats[resource_id] = entity_stats.get(resource_id, 0) + chunks

    def mark_failure(self, *, source_uri: str, error: str) -> None:
        self.files_failed += 1
        self.failures.append({"source_uri": source_uri, "error": error})

    def mark_skipped(self, *, entity_id: str, resource_id: str, chunks: int) -> None:
        self.files_skipped += 1

        entity_stats = self.by_entity.setdefault(entity_id, {})
        entity_stats["files_skipped"] = entity_stats.get("files_skipped", 0) + 1
        entity_stats[f"{resource_id}_skipped_chunks"] = (
            entity_stats.get(f"{resource_id}_skipped_chunks", 0) + chunks
        )

    def finish(self) -> None:
        self.completed_at = datetime.now(UTC)
