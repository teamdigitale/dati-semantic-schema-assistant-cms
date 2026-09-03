from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class IngestionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="local", alias="APP_ENV")
    project_id: str = Field(default="", alias="GOOGLE_CLOUD_PROJECT")
    location: str = Field(default="europe-west8", alias="GOOGLE_CLOUD_LOCATION")
    firestore_database: str = Field(default="(default)", alias="FIRESTORE_DATABASE")
    bucket_name: str = Field(default="", alias="SCHEMA_ASSISTANT_BUCKET")
    chunks_collection_group: str = Field(
        default="chunks", alias="FIRESTORE_CHUNKS_COLLECTION_GROUP"
    )

    embedding_model: str = Field(default="gemini-embedding-001", alias="EMBEDDING_MODEL")
    embedding_dimension: int = Field(default=2048, alias="EMBEDDING_DIMENSION")
    embedding_batch_size: int = Field(default=16, alias="EMBEDDING_BATCH_SIZE")
    firestore_write_batch_size: int = Field(
        default=50,
        alias="INGESTION_FIRESTORE_WRITE_BATCH_SIZE",
    )

    entities_config_path: Path = Field(
        default=Path("config/entities_config.json"),
        alias="ENTITIES_CONFIG_PATH",
    )
    local_docs_dir: Path | None = Field(default=None, alias="INGESTION_DOCS_DIR")
    gcs_docs_prefix: str | None = Field(
        default=None,
        alias="INGESTION_GCS_DOCS_PREFIX",
    )

    max_chunk_chars: int = Field(default=3500, alias="INGESTION_MAX_CHUNK_CHARS")
    chunk_overlap_chars: int = Field(default=300, alias="INGESTION_CHUNK_OVERLAP_CHARS")
    max_triples_per_file: int = Field(default=600, alias="INGESTION_MAX_TRIPLES_PER_FILE")
    dry_run: bool = Field(default=False, alias="INGESTION_DRY_RUN")

    @field_validator(
        "embedding_batch_size",
        "embedding_dimension",
        "firestore_write_batch_size",
        "max_chunk_chars",
        "max_triples_per_file",
    )
    @classmethod
    def _positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("value must be positive")
        return value

    @field_validator("embedding_dimension")
    @classmethod
    def _valid_embedding_dimension(cls, value: int) -> int:
        if value > 2048:
            raise ValueError("Firestore vector indexes support dimensions up to 2048")
        return value

    @field_validator("chunk_overlap_chars")
    @classmethod
    def _valid_overlap(cls, value: int) -> int:
        if value < 0:
            raise ValueError("chunk overlap cannot be negative")
        return value

    @field_validator("firestore_write_batch_size")
    @classmethod
    def _valid_firestore_write_batch_size(cls, value: int) -> int:
        if value > 450:
            raise ValueError("Firestore batch size cannot be higher than 450")
        return value

    @field_validator("gcs_docs_prefix")
    @classmethod
    def _valid_gcs_docs_prefix(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.replace("\\", "/").strip("/")
        if not cleaned or ".." in cleaned.split("/"):
            raise ValueError("GCS docs prefix must be a safe object prefix")
        return cleaned


@lru_cache(maxsize=1)
def get_settings() -> IngestionSettings:
    return IngestionSettings()
