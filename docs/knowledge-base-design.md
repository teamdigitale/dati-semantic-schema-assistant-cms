# Knowledge base storage design

The knowledge base uses two Google Cloud services:

- Cloud Storage stores original and processed assets.
- Firestore stores metadata, text chunks, and vector embeddings.

The chat service is stateless. User memory stays in the browser; Firestore does
not store conversations.

## Cloud Storage

Prefixes separate operator uploads, downloaded sources, processed assets, and
reports:

```text
incoming/docs/{filename}
raw/github/{entity}/{resource}/{source_hash}/{file_path}
raw/docs/{source_hash}/{filename}
processed/{entity}/{resource}/{source_hash}.json
reports/ingestion/{timestamp}.json
```

`incoming/docs/` is the manual source for PDF and CSV files. The job downloads
these files into `/tmp` and never embeds them in the Docker image. `raw/docs/`
remains available for local development sources.

## Firestore

Chunks are stored in subcollections with stable source-derived shards:

```text
entities/{entity}
entities/{entity}/resources/{resource}
entities/{entity}/resources/{resource}/sources/{source_hash}
entities/{entity}/resources/{resource}/source_index/{source_uri_hash}
entities/{entity}/resources/{resource}/asset_index/{source_uri_hash}
entities/{entity}/resources/{resource}/shards/{shard}/chunks/{chunk_id}
```

The chunk collection group is always `chunks`, so one vector index is created
on the `embedding` field for that collection group. `source_uri` identifies a
logical file; `source_hash` identifies its content version. A completed source
with the same URI and hash is skipped. A changed file gets a new hash and is
processed again.

`asset_index/{source_uri_hash}` contains compact metadata such as title, path,
format, extracted labels, keywords, and Cloud Storage pointers. It supports
deterministic list, comparison, and count questions. The job refreshes this
index even when embedding generation is skipped.

## Embeddings and queries

Firestore vector indexes support at most 2048 dimensions. Therefore
`EMBEDDING_DIMENSION` is fixed at `2048`, even if the Vertex model can produce
larger vectors.

Vector search runs on the `chunks` collection group. When routing identifies an
entity, resource type, or both, Firestore prefilters on `entity_id` and/or
`resource_id` before nearest-neighbor search. Composite indexes prevent the
application from reading unrelated global results and discarding them later.

For list and count questions, the agent uses `asset_index` when routing has
enough entity and resource signals. Vector search remains the main path for
semantic and descriptive questions. When routing narrows the search, the agent
also performs a small secondary search in `catalog/context_documents` so a
relevant guide is not excluded by the main filter.

Routing has two configuration layers:

- `config/resources.json` defines available technical resources.
- `config/routing_lexicon.json` contains domain synonyms and distinguishing
  signals used to associate questions with an entity.

## Ingestion

The manual job reads `config/entities_config.json`, clones GitHub repositories
into `/tmp`, uploads raw files to Cloud Storage, stores processed JSON, and
writes embedding chunks to Firestore. For NDC repositories it checks each
concept directory for supported files under `latest/`, then falls back to a
recursive search when that convention is absent.

Static PDF and CSV files belong under `incoming/docs/`. PDFs without a text
layer are reported as errors because they require OCR; partially readable PDFs
produce a warning with the number of extracted pages. `INGESTION_DOCS_DIR` is
reserved for focused local tests.

Ingestion is incremental: completed sources with the same URI and hash are
skipped, while sources left in `processing` (for example after a crash or OOM)
are retried.
