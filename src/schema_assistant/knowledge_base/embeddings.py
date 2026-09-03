from __future__ import annotations

import time
from collections.abc import Iterable

from google import genai
from google.genai import types


class VertexEmbeddingClient:
    def __init__(
        self,
        *,
        project_id: str,
        location: str,
        model: str,
        output_dimensionality: int = 2048,
        batch_size: int = 16,
        max_retries: int = 5,
    ) -> None:
        if not project_id:
            raise ValueError("project_id is required")
        if output_dimensionality <= 0 or output_dimensionality > 2048:
            raise ValueError("output_dimensionality must be between 1 and 2048")

        self._client = genai.Client(vertexai=True, project=project_id, location=location)
        self._model = model
        self._output_dimensionality = output_dimensionality
        self._batch_size = batch_size
        self._max_retries = max_retries

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for batch in _batches(texts, self._batch_size):
            vectors.extend(
                self._embed_with_retry(
                    batch,
                    task_type="RETRIEVAL_DOCUMENT",
                )
            )
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed_with_retry([text], task_type="RETRIEVAL_QUERY")[0]

    def _embed_with_retry(self, texts: list[str], *, task_type: str) -> list[list[float]]:
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._client.models.embed_content(
                    model=self._model,
                    contents=texts,
                    config=types.EmbedContentConfig(
                        output_dimensionality=self._output_dimensionality,
                        task_type=task_type,
                    ),
                )
                return [
                    [float(value) for value in embedding.values]
                    for embedding in response.embeddings
                ]
            except Exception as exc:
                last_error = exc
                if attempt == self._max_retries:
                    break
                time.sleep(min(2 ** (attempt - 1), 20))

        raise RuntimeError("Vertex embedding request failed") from last_error


def _batches(items: list[str], size: int) -> Iterable[list[str]]:
    if size <= 0:
        raise ValueError("batch size must be positive")
    for index in range(0, len(items), size):
        yield items[index : index + size]
