from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Protocol

from schema_assistant.knowledge_base.paths import stable_hash

if TYPE_CHECKING:
    from schema_assistant.knowledge_base.models import ResourceKind


class EntityLike(Protocol):
    name: str
    repo_url: object
    ontologies_folder: str
    schemas_folder: str
    vocabularies_folder: str


class StorageDocsReader(Protocol):
    bucket_name: str

    def list_paths(self, prefix: str) -> Iterable[str]: ...

    def download_to_path(self, object_path: str, destination: Path) -> None: ...

    def uri_for(self, object_path: str) -> str: ...


@dataclass(frozen=True)
class SourceFile:
    entity_id: str
    resource_id: ResourceKind
    path: Path
    relative_path: str
    source_uri: str
    repo_url: str | None = None
    origin_storage_uri: str | None = None


def discover_entity_files(entity: EntityLike, repo_dir: Path, assets_dir: Path) -> list[SourceFile]:
    files: list[SourceFile] = []

    resource_dirs: list[tuple[ResourceKind, Path, tuple[str, ...]]] = [
        ("ontologies", assets_dir / entity.ontologies_folder, (".ttl",)),
        ("ttl_schemas", assets_dir / entity.schemas_folder, (".ttl",)),
        ("yaml_schemas", assets_dir / entity.schemas_folder, (".yaml", ".yml")),
        ("vocabularies", assets_dir / entity.vocabularies_folder, (".ttl",)),
    ]

    for resource_id, resource_dir, extensions in resource_dirs:
        if not resource_dir.exists():
            continue

        for path in _iter_latest_files(resource_dir, extensions):
            relative_path = path.relative_to(repo_dir).as_posix()
            files.append(
                SourceFile(
                    entity_id=entity.name,
                    resource_id=resource_id,
                    path=path,
                    relative_path=relative_path,
                    source_uri=f"{entity.repo_url}#/{relative_path}",
                    repo_url=str(entity.repo_url),
                )
            )

    return files


def discover_local_docs(docs_dir: Path) -> list[SourceFile]:
    if not docs_dir.exists():
        return []

    files: list[SourceFile] = []
    for path in _iter_supported_files(docs_dir, (".pdf", ".csv")):
        relative_path = path.relative_to(docs_dir).as_posix()
        resource_id: ResourceKind = (
            "dates_collection" if path.suffix.lower() == ".csv" else "context_documents"
        )
        files.append(
            SourceFile(
                entity_id="catalog",
                resource_id=resource_id,
                path=path,
                relative_path=relative_path,
                source_uri=f"local-docs://{relative_path}",
            )
        )
    return files


def discover_storage_docs(
    storage: StorageDocsReader,
    prefix: str,
    target_dir: Path,
) -> list[SourceFile]:
    clean_prefix = prefix.replace("\\", "/").strip("/")
    prefix_with_separator = f"{clean_prefix}/"
    files: list[SourceFile] = []

    for object_path in sorted(storage.list_paths(clean_prefix)):
        if not object_path.startswith(prefix_with_separator):
            continue

        relative_path = object_path[len(prefix_with_separator) :]
        relative = PurePosixPath(relative_path)
        suffix = relative.suffix.lower()
        if (
            not relative_path
            or suffix not in {".pdf", ".csv"}
            or any(part.startswith(".") for part in relative.parts)
        ):
            continue

        local_path = target_dir / f"{stable_hash(object_path, length=24)}{suffix}"
        storage.download_to_path(object_path, local_path)
        storage_uri = storage.uri_for(object_path)
        resource_id: ResourceKind = "dates_collection" if suffix == ".csv" else "context_documents"
        files.append(
            SourceFile(
                entity_id="catalog",
                resource_id=resource_id,
                path=local_path,
                relative_path=relative_path,
                source_uri=storage_uri,
                origin_storage_uri=storage_uri,
            )
        )

    return files


def _iter_supported_files(root: Path, extensions: tuple[str, ...]) -> list[Path]:
    lower_extensions = tuple(item.lower() for item in extensions)
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in lower_extensions
        and not any(part.startswith(".") for part in path.relative_to(root).parts)
    )


def _iter_latest_files(root: Path, extensions: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    concept_dirs = sorted(
        path for path in root.iterdir() if path.is_dir() and not path.name.startswith(".")
    )

    if not concept_dirs:
        return _iter_supported_files(root, extensions)

    for concept_dir in concept_dirs:
        latest_dir = concept_dir / "latest"
        if latest_dir.is_dir():
            files.extend(_iter_direct_supported_files(latest_dir, extensions))
        else:
            # Some repositories do not follow the `concept/latest` layout. In that case
            # we keep the old fallback and scan the concept folder recursively.
            files.extend(_iter_supported_files(concept_dir, extensions))

    return sorted(files)


def _iter_direct_supported_files(root: Path, extensions: tuple[str, ...]) -> list[Path]:
    lower_extensions = tuple(item.lower() for item in extensions)
    return sorted(
        path
        for path in root.iterdir()
        if path.is_file()
        and path.suffix.lower() in lower_extensions
        and not path.name.startswith(".")
    )
