from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="local", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    project_id: str = Field(default="", alias="GOOGLE_CLOUD_PROJECT")
    location: str = Field(default="europe-west8", alias="GOOGLE_CLOUD_LOCATION")
    firestore_database: str = Field(default="(default)", alias="FIRESTORE_DATABASE")
    bucket_name: str = Field(default="", alias="SCHEMA_ASSISTANT_BUCKET")

    chat_model: str = Field(default="gemini-2.5-flash", alias="CHAT_MODEL")
    embedding_model: str = Field(default="gemini-embedding-001", alias="EMBEDDING_MODEL")
    embedding_dimension: int = Field(default=2048, alias="EMBEDDING_DIMENSION")
    firestore_chunks_collection_group: str = Field(
        default="chunks",
        alias="FIRESTORE_CHUNKS_COLLECTION_GROUP",
    )
    llm_enabled: bool = Field(default=True, alias="LLM_ENABLED")
    rag_enabled: bool = Field(default=False, alias="RAG_ENABLED")
    rag_top_k: int = Field(default=8, alias="RAG_TOP_K")
    rag_context_max_chars: int = Field(default=12000, alias="RAG_CONTEXT_MAX_CHARS")
    rag_max_distance: float = Field(default=0.45, alias="RAG_MAX_DISTANCE")
    resources_config_path: Path = Field(
        default=Path("config/resources.json"),
        alias="RESOURCES_CONFIG_PATH",
    )
    routing_lexicon_config_path: Path = Field(
        default=Path("config/routing_lexicon.json"),
        alias="ROUTING_LEXICON_CONFIG_PATH",
    )
    entities_config_path: Path = Field(
        default=Path("config/entities_config.json"),
        alias="ENTITIES_CONFIG_PATH",
    )

    max_input_chars: int = Field(default=4000, alias="MAX_INPUT_CHARS")
    max_history_messages: int = Field(default=12, alias="MAX_HISTORY_MESSAGES")
    max_history_message_chars: int = Field(default=2000, alias="MAX_HISTORY_MESSAGE_CHARS")
    max_output_tokens: int = Field(default=2048, alias="MAX_OUTPUT_TOKENS")
    thinking_budget: int = Field(default=512, alias="THINKING_BUDGET")
    request_timeout_seconds: float = Field(default=30.0, alias="REQUEST_TIMEOUT_SECONDS")

    cost_status: Literal["green", "yellow", "red", "blocked"] = Field(
        default="green",
        alias="COST_STATUS",
    )

    @field_validator(
        "embedding_dimension",
        "max_input_chars",
        "max_history_messages",
        "max_output_tokens",
        "rag_context_max_chars",
        "rag_top_k",
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

    @field_validator("thinking_budget")
    @classmethod
    def _non_negative_int(cls, value: int) -> int:
        if value < 0:
            raise ValueError("value cannot be negative")
        return value

    @field_validator("rag_max_distance")
    @classmethod
    def _valid_rag_max_distance(cls, value: float) -> float:
        if not 0 < value <= 2:
            raise ValueError("rag_max_distance must be greater than 0 and no higher than 2")
        return value


@lru_cache(maxsize=1)
def get_settings() -> AgentSettings:
    return AgentSettings()
