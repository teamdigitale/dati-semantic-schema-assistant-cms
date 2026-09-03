from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from schema_assistant.agent.config import AgentSettings, get_settings
from schema_assistant.agent.models import ChatMessage
from schema_assistant.knowledge_base.embeddings import VertexEmbeddingClient
from schema_assistant.knowledge_base.firestore_store import FirestoreVectorStore
from schema_assistant.knowledge_base.models import MetadataSearchResult, ResourceKind, SearchResult

CATALOG_KEYWORDS = {"schema.gov.it", "catalogo", "interoperabilita", "documento", "documenti"}
CATALOG_RESOURCES = {"context_documents", "dates_collection"}
GENERIC_ENTITY_HINTS = {
    "attivita",
    "categoria",
    "classificazione",
    "classe",
    "codice",
    "commercio",
    "economia",
    "ente",
    "industria",
    "produzione",
    "risorsa",
    "risorse",
    "schema",
    "servizi",
    "settore",
    "tipologia",
    "vocabolario",
    "vocabolari",
}
FOLLOW_UP_PREFIXES = (
    "anche per ",
    "e invece ",
    "e per ",
    "in quel caso",
    "in questo caso",
    "invece ",
    "nel caso ",
)
FOLLOW_UP_QUESTIONS = (
    "avete codici",
    "ce ne sono altri",
    "come mai",
    "dimmi di piu",
    "hai codici",
    "mi dai i codici",
    "perche",
    "puoi dirmi di piu",
    "puoi indicarmi i codici",
    "quali codici",
)
ATECO_PANINARO_EXPANSIONS = (
    "codice ATECO ristorazione ambulante preparazione e vendita di panini",
    "codice ATECO preparazione di cibi da asporto vendita ambulante di alimenti e bevande",
)
ATECO_PANINARO_FIXED_EXPANSIONS = (
    "codice ATECO preparazione e vendita di panini in sede fissa",
    "codice ATECO ristorazione senza somministrazione preparazione di cibi da asporto",
)


@dataclass(frozen=True)
class RetrievalResult:
    context: str
    sources: list[str]
    chunks: list[SearchResult]
    metadata_assets: list[MetadataSearchResult]
    detected_entities: set[str]
    detected_resources: set[str]
    listing_question: bool
    context_document_chunks: int
    has_relevant_context: bool
    best_distance: float | None
    discarded_chunks: int
    query_variants: int
    history_context_used: bool


class KnowledgeBaseRetriever:
    def __init__(self, settings: AgentSettings) -> None:
        self._settings = settings
        self._resource_keywords = _load_resource_keywords(
            settings.resources_config_path,
            settings.routing_lexicon_config_path,
        )
        self._entity_ids = _load_entity_ids(settings.entities_config_path)
        self._entity_hints = _load_entity_hints(
            settings.routing_lexicon_config_path,
            entity_ids=self._entity_ids,
        )
        self._embeddings = VertexEmbeddingClient(
            project_id=settings.project_id,
            location=settings.location,
            model=settings.embedding_model,
            output_dimensionality=settings.embedding_dimension,
        )
        self._store = FirestoreVectorStore(
            project_id=settings.project_id,
            database=settings.firestore_database,
            chunks_collection_group=settings.firestore_chunks_collection_group,
        )

    def retrieve(
        self,
        question: str,
        history: Sequence[ChatMessage] = (),
    ) -> RetrievalResult:
        retrieval_queries, history_context_used = _build_retrieval_queries(question, history)
        routing_question = retrieval_queries[0]
        detected_entities = _detect_entities(
            routing_question,
            self._entity_hints,
            entity_ids=self._entity_ids,
        )
        detected_resources = _detect_resources(routing_question, self._resource_keywords)
        entity_filter = _entity_filter_for_resources(detected_entities, detected_resources)
        listing_question = _is_listing_question(routing_question)
        search_limit = (
            self._settings.rag_top_k * 2 if listing_question else self._settings.rag_top_k
        )
        context_max_chars = (
            self._settings.rag_context_max_chars * 2
            if listing_question
            else self._settings.rag_context_max_chars
        )
        metadata_assets = self._metadata_assets(
            question=routing_question,
            entity_filter=entity_filter,
            detected_resources=detected_resources,
            listing_question=listing_question,
        )

        query_vectors = [self._embeddings.embed_query(query) for query in retrieval_queries]
        chunks: list[SearchResult] = []
        for query_vector in query_vectors:
            query_chunks = self._store.search(
                query_vector,
                limit=search_limit,
                entity_ids=entity_filter,
                resource_ids=detected_resources or None,
            )
            chunks = _merge_search_results(chunks, query_chunks, limit=search_limit)

        if _should_search_context_documents(entity_filter, detected_resources):
            document_chunks = self._store.search(
                query_vectors[0],
                limit=max(3, min(6, self._settings.rag_top_k // 2)),
                entity_ids={"catalog"},
                resource_ids={"context_documents"},
            )
            chunks = _merge_search_results(chunks, document_chunks, limit=search_limit)

        best_distance = _best_distance(chunks)
        discarded_chunks = len(chunks)
        chunks = _filter_relevant_chunks(chunks, max_distance=self._settings.rag_max_distance)
        discarded_chunks -= len(chunks)
        has_relevant_context = bool(chunks)
        if not has_relevant_context:
            metadata_assets = []

        context = _join_contexts(
            _build_metadata_context(metadata_assets),
            _build_context(chunks, max_chars=context_max_chars) if chunks else None,
        )
        if not context:
            context = _empty_context()
        sources = _dedupe_sources(chunks, metadata_assets)
        return RetrievalResult(
            context=context,
            sources=sources,
            chunks=chunks,
            metadata_assets=metadata_assets,
            detected_entities=detected_entities,
            detected_resources=detected_resources,
            listing_question=listing_question,
            context_document_chunks=sum(
                chunk.resource_id == "context_documents" for chunk in chunks
            ),
            has_relevant_context=has_relevant_context,
            best_distance=best_distance,
            discarded_chunks=discarded_chunks,
            query_variants=len(retrieval_queries),
            history_context_used=history_context_used,
        )

    def _metadata_assets(
        self,
        *,
        question: str,
        entity_filter: set[str] | None,
        detected_resources: set[str],
        listing_question: bool,
    ) -> list[MetadataSearchResult]:
        if not listing_question or not entity_filter or not detected_resources:
            return []

        assets = self._store.list_asset_metadata(
            entity_ids=entity_filter,
            resource_ids=detected_resources,
        )
        terms = _important_terms(question)
        scored_assets = [
            (asset, _metadata_score(asset, terms))
            for asset in assets
            if not terms or _metadata_score(asset, terms) > 0
        ]
        if not scored_assets:
            return sorted(assets, key=lambda asset: (asset.entity_id, asset.title))[:40]

        scored_assets.sort(key=lambda item: (-item[1], item[0].entity_id, item[0].title))
        return [asset for asset, _score in scored_assets[:40]]


@lru_cache(maxsize=1)
def get_knowledge_base_retriever() -> KnowledgeBaseRetriever:
    return KnowledgeBaseRetriever(get_settings())


def _build_retrieval_queries(
    question: str,
    history: Sequence[ChatMessage],
) -> tuple[list[str], bool]:
    previous_user_message = _last_user_message(history)
    history_context_used = bool(previous_user_message and _is_context_dependent_question(question))
    primary_query = (
        f"{previous_user_message}\nApprofondimento: {question}"
        if history_context_used
        else question
    )
    queries = [primary_query, *_ateco_query_expansions(primary_query)]
    return _dedupe_queries(queries), history_context_used


def _last_user_message(history: Sequence[ChatMessage]) -> str | None:
    return next((item.content for item in reversed(history) if item.role == "user"), None)


def _is_context_dependent_question(question: str) -> bool:
    normalized = _normalize_text(question).strip(" .?!,:;")
    if not normalized:
        return False
    if normalized == "approfondisci":
        return True
    if any(normalized.startswith(prefix) for prefix in FOLLOW_UP_PREFIXES):
        return True
    return any(normalized.startswith(pattern) for pattern in FOLLOW_UP_QUESTIONS)


def _ateco_query_expansions(question: str) -> tuple[str, ...]:
    normalized = _normalize_text(question)
    if not _contains_term(normalized, "ateco") or not _contains_term(normalized, "paninaro"):
        return ()
    if any(term in normalized for term in ("attivita fissa", "sede fissa", "locale fisso")):
        return ATECO_PANINARO_FIXED_EXPANSIONS
    return ATECO_PANINARO_EXPANSIONS


def _dedupe_queries(queries: Sequence[str]) -> list[str]:
    deduplicated: list[str] = []
    seen: set[str] = set()
    for query in queries:
        normalized = _normalize_text(query)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduplicated.append(query.strip())
    return deduplicated


def _load_resource_keywords(*paths: Path) -> dict[ResourceKind, list[str]]:
    keywords: dict[ResourceKind, list[str]] = {}
    for path in paths:
        if not path.exists():
            continue

        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)

        for resource_id, config in payload.items():
            if not isinstance(config, dict):
                continue
            raw_keywords = config.get("keywords") or []
            current_keywords = keywords.setdefault(resource_id, [])
            current_keywords.extend(str(item).lower() for item in raw_keywords if str(item).strip())
    for resource_id, values in keywords.items():
        keywords[resource_id] = sorted(set(values))
    return keywords


def _load_entity_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()

    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    raw_entities = payload.get("entities")
    if not isinstance(raw_entities, list):
        return set()

    return {
        _normalize_text(str(entity.get("name")))
        for entity in raw_entities
        if isinstance(entity, dict) and _normalize_text(str(entity.get("name") or ""))
    }


def _load_entity_hints(
    path: Path,
    *,
    entity_ids: set[str] | None = None,
) -> dict[str, list[str]]:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    raw_hints = payload.get("entity_hints")
    if not isinstance(raw_hints, dict):
        return {}

    hints: dict[str, list[str]] = {}
    for entity_id, config in raw_hints.items():
        normalized_entity_id = _normalize_text(str(entity_id))
        if (
            not isinstance(config, dict)
            or entity_ids is not None
            and normalized_entity_id not in entity_ids
        ):
            continue
        raw_keywords = config.get("keywords") or []
        keywords = {
            _normalize_text(str(keyword))
            for keyword in raw_keywords
            if _normalize_text(str(keyword))
        }
        if keywords:
            hints[normalized_entity_id] = sorted(
                keywords,
                key=lambda keyword: (-len(keyword), keyword),
            )
    return hints


def _detect_entities(
    question: str,
    entity_hints: dict[str, list[str]] | None = None,
    *,
    entity_ids: set[str] | None = None,
) -> set[str]:
    normalized = _normalize_text(question)
    detected = {
        entity_id for entity_id in entity_ids or set() if _matches_entity_id(normalized, entity_id)
    }
    if not detected and entity_hints:
        entity_scores = {
            entity_id: _entity_hint_score(normalized, keywords)
            for entity_id, keywords in entity_hints.items()
        }
        highest_score = max(entity_scores.values(), default=0)
        # A routing hint must be distinctive. Common words alone are not allowed
        # to narrow a search to a single entity.
        if highest_score >= 3:
            detected = {
                entity_id for entity_id, score in entity_scores.items() if score == highest_score
            }
    if any(keyword in normalized for keyword in CATALOG_KEYWORDS):
        detected.add("catalog")
    return detected


def _matches_entity_id(question: str, entity_id: str) -> bool:
    normalized_entity_id = _normalize_text(entity_id)
    variants = {
        normalized_entity_id,
        normalized_entity_id.replace("-", " "),
    }
    return any(_contains_term(question, variant) for variant in variants if variant)


def _detect_resources(
    question: str,
    resource_keywords: dict[ResourceKind, list[str]],
) -> set[str]:
    normalized = _normalize_text(question)
    detected: set[str] = set()

    date_words = {"data", "date", "quando", "pubblicazione", "creazione", "immissione"}
    if any(word in normalized for word in date_words):
        detected.add("dates_collection")

    for resource_id, keywords in resource_keywords.items():
        if any(_contains_term(normalized, keyword) for keyword in keywords):
            detected.add(resource_id)

    return detected


def _entity_filter_for_resources(
    detected_entities: set[str],
    detected_resources: set[str],
) -> set[str] | None:
    if detected_resources and detected_resources.issubset(CATALOG_RESOURCES):
        return {"catalog"}
    return detected_entities or None


def _should_search_context_documents(
    entity_filter: set[str] | None,
    detected_resources: set[str],
) -> bool:
    if entity_filter is None and not detected_resources:
        return False
    if detected_resources == {"dates_collection"}:
        return False
    return not (
        entity_filter is not None
        and "catalog" in entity_filter
        and "context_documents" in detected_resources
    )


def _merge_search_results(
    primary: list[SearchResult],
    secondary: list[SearchResult],
    *,
    limit: int,
) -> list[SearchResult]:
    deduplicated: dict[str, SearchResult] = {}
    for result in [*primary, *secondary]:
        existing = deduplicated.get(result.chunk_id)
        if existing is None or _search_distance(result) < _search_distance(existing):
            deduplicated[result.chunk_id] = result
    return sorted(deduplicated.values(), key=_search_distance)[:limit]


def _search_distance(result: SearchResult) -> float:
    return result.distance if result.distance is not None else float("inf")


def _best_distance(chunks: list[SearchResult]) -> float | None:
    best_distance = min((_search_distance(chunk) for chunk in chunks), default=float("inf"))
    return best_distance if best_distance != float("inf") else None


def _filter_relevant_chunks(
    chunks: list[SearchResult],
    *,
    max_distance: float,
) -> list[SearchResult]:
    return [chunk for chunk in chunks if _search_distance(chunk) <= max_distance]


def _build_context(chunks: list[SearchResult], *, max_chars: int) -> str:
    if not chunks:
        return _empty_context()

    blocks: list[str] = []
    used_chars = 0
    for index, chunk in enumerate(chunks, start=1):
        text = _sanitize_context_content(chunk.content)
        if not text:
            continue

        block = (
            f"Estratto {index}\n"
            f"Ente: {chunk.entity_id}\n"
            f"Risorsa: {chunk.resource_id}\n"
            f"Contenuto:\n{text}"
        )
        remaining = max_chars - used_chars
        if remaining <= 0:
            break
        if len(block) > remaining:
            block = block[:remaining].rstrip()
        blocks.append(block)
        used_chars += len(block)

    return "\n\n---\n\n".join(blocks)


def _build_metadata_context(assets: list[MetadataSearchResult]) -> str | None:
    if not assets:
        return None

    lines = [
        "Indice metadata degli asset pertinenti.",
        "Usa questo indice per domande di elenco, confronto o conteggio.",
    ]
    for index, asset in enumerate(assets, start=1):
        labels = "; ".join(asset.labels[:8])
        keywords = "; ".join(asset.keywords[:12])
        lines.append(
            "\n".join(
                item
                for item in [
                    f"Asset {index}",
                    f"Ente: {asset.entity_id}",
                    f"Risorsa: {asset.resource_id}",
                    f"Titolo: {asset.title}",
                    f"Percorso: {asset.relative_path}",
                    f"Formato: {asset.format or asset.content_type}",
                    f"Label: {labels}" if labels else "",
                    f"Keyword: {keywords}" if keywords else "",
                ]
                if item
            )
        )
    return "\n\n---\n\n".join(lines)


def _empty_context() -> str:
    return (
        "Nessun contesto e stato trovato nella knowledge base per questa domanda. "
        "Rispondi dichiarando che non hai informazioni sufficienti."
    )


def _join_contexts(*contexts: str | None) -> str:
    return "\n\n===\n\n".join(context for context in contexts if context)


def _sanitize_context_content(content: str) -> str:
    lines = []
    for line in content.splitlines():
        stripped = line.strip()
        if re.match(r"^(fonte|source|uri)\s*:", stripped, flags=re.IGNORECASE):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _dedupe_sources(
    chunks: list[SearchResult],
    metadata_assets: list[MetadataSearchResult] | None = None,
) -> list[str]:
    sources = []
    seen = set()
    for source in [
        *(asset.source_uri for asset in metadata_assets or []),
        *(chunk.source_uri for chunk in chunks),
    ]:
        if source in seen:
            continue
        seen.add(source)
        sources.append(source)
    return sources


def _normalize_text(value: str) -> str:
    lowered = value.lower().replace("'", " ")
    decomposed = unicodedata.normalize("NFKD", lowered)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_accents).strip()


def _contains_term(text: str, term: str) -> bool:
    normalized_term = _normalize_text(term)
    if not normalized_term:
        return False
    return re.search(rf"(?<!\w){re.escape(normalized_term)}(?!\w)", text) is not None


def _entity_hint_score(question: str, keywords: list[str]) -> int:
    score = 0
    for keyword in keywords:
        if keyword in GENERIC_ENTITY_HINTS or not _contains_term(question, keyword):
            continue
        words = keyword.split()
        if len(words) >= 2:
            score = max(score, 4 + len(words))
        elif len(keyword) >= 5:
            score = max(score, 3)
    return score


def _is_listing_question(question: str) -> bool:
    normalized = _normalize_text(question)
    listing_keywords = {
        "elenca",
        "elenco",
        "lista",
        "quali",
        "quanti",
        "quante",
        "numero",
        "totale",
        "distinti",
        "distinte",
        "combinano",
        "combinate",
        "tutte",
        "tutti",
        "pubblicato",
        "pubblicati",
        "pubblicate",
        "risorse",
        "ontologie",
        "vocabolari",
        "classificazione",
        "classificazioni",
        "schemi",
    }
    return any(keyword in normalized for keyword in listing_keywords)


def _important_terms(question: str) -> set[str]:
    stop_words = {
        "agli",
        "alla",
        "alle",
        "associati",
        "classificazioni",
        "combinano",
        "combinate",
        "come",
        "con",
        "degli",
        "delle",
        "distinti",
        "distinte",
        "inail",
        "inps",
        "istat",
        "italia",
        "numero",
        "ontologie",
        "quale",
        "quali",
        "quando",
        "risorse",
        "schemi",
        "sono",
        "totale",
        "vocabolari",
    }
    normalized = _normalize_text(question)
    return {
        token
        for token in re.findall(r"\w{4,}", normalized)
        if token not in stop_words and not token.isdigit()
    }


def _metadata_score(asset: MetadataSearchResult, terms: set[str]) -> int:
    search_text = _normalize_text(
        " ".join(
            [
                asset.title,
                asset.relative_path,
                " ".join(asset.labels),
                " ".join(asset.keywords),
            ]
        )
    )
    return sum(1 for term in terms if term in search_text)
