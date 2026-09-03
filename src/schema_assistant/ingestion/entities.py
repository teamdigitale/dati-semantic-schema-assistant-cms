from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class EntityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    repo_url: HttpUrl
    assets_path: str = ""
    ontologies_folder: str
    schemas_folder: str
    vocabularies_folder: str
    collections: dict[str, str] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _valid_name(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("entity name cannot be empty")
        return cleaned


class EntitiesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entities: list[EntityConfig]


def load_entities_config(path: Path) -> list[EntityConfig]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    config = EntitiesConfig.model_validate(payload)
    return cast(list[EntityConfig], config.entities)
