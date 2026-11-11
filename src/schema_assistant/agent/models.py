from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ChatModelPart(BaseModel):
    model_config = ConfigDict(extra="forbid", ser_json_bytes="base64", val_json_bytes="base64")

    text: str | None = Field(default=None, max_length=16_384)
    thought: Literal[False] | None = None
    thought_signature: bytes | None = Field(default=None, min_length=1, max_length=16_384)


class ChatModelContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["model"]
    parts: list[ChatModelPart] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def _require_signature(self) -> "ChatModelContent":
        if not any(part.thought_signature for part in self.parts):
            raise ValueError("model content must contain a thought signature")
        return self


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)
    model_content: ChatModelContent | None = None

    @model_validator(mode="after")
    def _validate_model_role(self) -> "ChatMessage":
        if self.model_content is not None and self.role != "assistant":
            raise ValueError("model content belongs to assistant messages")
        return self

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("content cannot be empty")
        return stripped


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)

    @field_validator("message")
    @classmethod
    def _strip_message(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("message cannot be empty")
        return stripped


class ChatUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    finish_reason: str | None = None


class ChatResponse(BaseModel):
    answer: str
    model_content: ChatModelContent | None = None
    sources: list[str] = Field(default_factory=list)
    usage: ChatUsage = Field(default_factory=ChatUsage)
    cost_status: Literal["green", "yellow", "red", "blocked"]
    rag_enabled: bool
    request_id: str


class ErrorResponse(BaseModel):
    detail: str
    request_id: str | None = None
