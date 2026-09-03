from pathlib import Path
from types import SimpleNamespace

from schema_assistant.ingestion.discovery import (
    discover_entity_files,
    discover_local_docs,
    discover_storage_docs,
)


def test_discover_entity_files_maps_resource_kinds(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    assets_dir = repo_dir / "assets"
    (assets_dir / "ontologies" / "concept" / "latest").mkdir(parents=True)
    (assets_dir / "ontologies" / "concept" / "old").mkdir()
    (assets_dir / "schemas" / "schema-concept" / "latest").mkdir(parents=True)
    (assets_dir / "controlled-vocabularies" / "vocab-concept").mkdir(parents=True)
    (assets_dir / "ontologies" / "concept" / "latest" / "o.ttl").write_text("@prefix x: <x:> .")
    (assets_dir / "ontologies" / "concept" / "old" / "o.ttl").write_text("@prefix x: <x:> .")
    (assets_dir / "schemas" / "schema-concept" / "latest" / "s.ttl").write_text("@prefix x: <x:> .")
    (assets_dir / "schemas" / "schema-concept" / "latest" / "s.yaml").write_text("openapi: 3.0.0")
    (assets_dir / "controlled-vocabularies" / "vocab-concept" / "v.ttl").write_text(
        "@prefix x: <x:> ."
    )

    entity = SimpleNamespace(
        name="istat",
        repo_url="https://github.com/istat/example",
        ontologies_folder="ontologies",
        schemas_folder="schemas",
        vocabularies_folder="controlled-vocabularies",
    )

    resource_ids = [
        item.resource_id for item in discover_entity_files(entity, repo_dir, assets_dir)
    ]

    assert resource_ids == ["ontologies", "ttl_schemas", "yaml_schemas", "vocabularies"]

    relative_paths = [
        item.relative_path for item in discover_entity_files(entity, repo_dir, assets_dir)
    ]
    assert "assets/ontologies/concept/old/o.ttl" not in relative_paths


def test_discover_local_docs_maps_pdf_and_csv(tmp_path: Path) -> None:
    (tmp_path / "guide.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "date.csv").write_text("name,date\nA,2026-01-01\n")

    resource_ids = [item.resource_id for item in discover_local_docs(tmp_path)]

    assert resource_ids == ["dates_collection", "context_documents"]


def test_discover_storage_docs_downloads_supported_objects(tmp_path: Path) -> None:
    storage = _FakeStorage(
        {
            "incoming/docs/guide.pdf": b"%PDF-1.4",
            "incoming/docs/nested/date.csv": b"name,date\nA,2026-01-01\n",
            "incoming/docs/notes.txt": b"ignored",
        }
    )

    sources = discover_storage_docs(storage, "incoming/docs", tmp_path)

    assert [source.resource_id for source in sources] == [
        "context_documents",
        "dates_collection",
    ]
    assert [source.relative_path for source in sources] == [
        "guide.pdf",
        "nested/date.csv",
    ]
    assert all(source.path.exists() for source in sources)
    assert sources[0].source_uri == "gs://test-bucket/incoming/docs/guide.pdf"
    assert sources[0].origin_storage_uri == sources[0].source_uri


class _FakeStorage:
    bucket_name = "test-bucket"

    def __init__(self, objects: dict[str, bytes]) -> None:
        self._objects = objects

    def list_paths(self, prefix: str) -> list[str]:
        prefix_with_separator = f"{prefix.rstrip('/')}/"
        return [path for path in self._objects if path.startswith(prefix_with_separator)]

    def download_to_path(self, object_path: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self._objects[object_path])

    def uri_for(self, object_path: str) -> str:
        return f"gs://{self.bucket_name}/{object_path}"
