from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import cast

from google.cloud import storage


class ObjectStorage:
    def __init__(self, bucket_name: str, project_id: str | None = None) -> None:
        if not bucket_name:
            raise ValueError("bucket_name is required")

        self._client = storage.Client(project=project_id)
        self._bucket = self._client.bucket(bucket_name)
        self.bucket_name = bucket_name

    def upload_bytes(
        self,
        object_path: str,
        content: bytes,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> str:
        blob = self._bucket.blob(_clean_object_path(object_path))
        if metadata:
            blob.metadata = metadata
        blob.upload_from_string(content, content_type=content_type)
        return self.uri_for(object_path)

    def upload_text(
        self,
        object_path: str,
        content: str,
        *,
        content_type: str = "text/plain; charset=utf-8",
        metadata: dict[str, str] | None = None,
    ) -> str:
        return self.upload_bytes(
            object_path,
            content.encode("utf-8"),
            content_type=content_type,
            metadata=metadata,
        )

    def download_text(self, object_path: str) -> str:
        blob = self._bucket.blob(_clean_object_path(object_path))
        return cast(str, blob.download_as_text(encoding="utf-8"))

    def download_to_path(self, object_path: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        blob = self._bucket.blob(_clean_object_path(object_path))
        blob.download_to_filename(str(destination))

    def exists(self, object_path: str) -> bool:
        blob = self._bucket.blob(_clean_object_path(object_path))
        return bool(blob.exists(client=self._client))

    def list_paths(self, prefix: str) -> Iterable[str]:
        clean_prefix = _clean_object_path(prefix).rstrip("/") + "/"
        for blob in self._client.list_blobs(self._bucket, prefix=clean_prefix):
            yield blob.name

    def uri_for(self, object_path: str) -> str:
        return f"gs://{self.bucket_name}/{_clean_object_path(object_path)}"


def _clean_object_path(object_path: str) -> str:
    cleaned = object_path.replace("\\", "/").strip("/")
    if not cleaned or cleaned == "." or ".." in cleaned.split("/"):
        raise ValueError("object_path contains an unsafe segment")
    return cleaned
