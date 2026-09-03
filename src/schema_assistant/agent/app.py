import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from schema_assistant.agent.config import get_settings
from schema_assistant.agent.guardrails import validate_chat_request
from schema_assistant.agent.logging import configure_logging
from schema_assistant.agent.models import ChatRequest, ChatResponse, ChatUsage, ErrorResponse
from schema_assistant.agent.prompts import build_system_instruction
from schema_assistant.agent.response_guardrails import enforce_response_policy
from schema_assistant.agent.retrieval import RetrievalResult, get_knowledge_base_retriever
from schema_assistant.agent.static_answers import find_static_answer
from schema_assistant.agent.vertex_client import get_vertex_chat_client

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Schema Assistant Agent",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.app_env != "prod" else None,
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(detail=str(exc.detail), request_id=request_id).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.warning(
        "request_validation_failed",
        extra={"request_id": request_id, "errors": exc.errors()},
    )
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(detail="Payload non valido.", request_id=request_id).model_dump(),
    )


@app.middleware("http")
async def add_request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    start_time = time.perf_counter()
    request.state.request_id = request_id

    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed", extra={"request_id": request_id})
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                detail="Errore interno del servizio.",
                request_id=request_id,
            ).model_dump(),
        )

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    response.headers["x-request-id"] = request_id
    logger.info(
        "request_completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok", "service": "schema-assistant-agent"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest, http_request: Request) -> ChatResponse | JSONResponse:
    request_id = http_request.state.request_id
    validate_chat_request(request, settings)

    static_answer = find_static_answer(request.message)
    if static_answer:
        logger.info(
            "static_answer_completed",
            extra={
                "request_id": request_id,
                "reason": static_answer.reason,
                "rag_enabled": settings.rag_enabled,
            },
        )
        return ChatResponse(
            answer=static_answer.answer,
            sources=[],
            usage=ChatUsage(input_tokens=0, output_tokens=0, total_tokens=0),
            cost_status=settings.cost_status,
            rag_enabled=settings.rag_enabled,
            request_id=request_id,
        )

    if not settings.llm_enabled:
        return ChatResponse(
            answer="Il modello e temporaneamente disabilitato per controlli operativi.",
            usage=ChatUsage(),
            cost_status=settings.cost_status,
            rag_enabled=settings.rag_enabled,
            request_id=request_id,
        )

    retrieval_result: RetrievalResult | None = None
    if settings.rag_enabled:
        try:
            retrieval_result = get_knowledge_base_retriever().retrieve(
                request.message,
                request.history,
            )
        except Exception:
            logger.exception("rag_retrieval_failed", extra={"request_id": request_id})
            return JSONResponse(
                status_code=502,
                content=ErrorResponse(
                    detail="La knowledge base non e al momento raggiungibile.",
                    request_id=request_id,
                ).model_dump(),
            )
        if not retrieval_result.has_relevant_context:
            logger.info(
                "chat_out_of_scope",
                extra={
                    "request_id": request_id,
                    "rag_best_distance": retrieval_result.best_distance,
                    "rag_max_distance": settings.rag_max_distance,
                    "rag_discarded_chunks": retrieval_result.discarded_chunks,
                },
            )
            return ChatResponse(
                answer=(
                    "Posso rispondere solo usando le informazioni presenti nel catalogo "
                    "e nelle risorse semantiche disponibili nella knowledge base. "
                    "Non ho contenuti pertinenti per questa domanda."
                ),
                sources=[],
                usage=ChatUsage(input_tokens=0, output_tokens=0, total_tokens=0),
                cost_status=settings.cost_status,
                rag_enabled=True,
                request_id=request_id,
            )
    else:
        return ChatResponse(
            answer=(
                "La knowledge base non e abilitata: non posso rispondere a domande "
                "che richiedono contenuti del catalogo."
            ),
            sources=[],
            usage=ChatUsage(input_tokens=0, output_tokens=0, total_tokens=0),
            cost_status=settings.cost_status,
            rag_enabled=False,
            request_id=request_id,
        )

    try:
        model_context = retrieval_result.context if retrieval_result else None
        result = get_vertex_chat_client().answer(
            request.message,
            request.history,
            context=model_context,
        )
    except Exception:
        logger.exception("vertex_chat_failed", extra={"request_id": request_id})
        return JSONResponse(
            status_code=502,
            content=ErrorResponse(
                detail="Il modello non e al momento raggiungibile.",
                request_id=request_id,
            ).model_dump(),
        )

    guarded_response = enforce_response_policy(
        result.answer,
        system_instruction=build_system_instruction(has_context=bool(model_context)),
        user_message=request.message,
    )
    if guarded_response.intervened:
        logger.warning(
            "chat_response_guardrail_applied",
            extra={
                "request_id": request_id,
                "reason": guarded_response.reason,
            },
        )
    elif guarded_response.language_mismatch_observed:
        logger.info(
            "chat_language_mismatch_observed",
            extra={"request_id": request_id},
        )

    logger.info(
        "chat_completed",
        extra={
            "request_id": request_id,
            "cost_status": settings.cost_status,
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "total_tokens": result.usage.total_tokens,
            "finish_reason": result.usage.finish_reason,
            "thinking_budget": settings.thinking_budget,
            "max_output_tokens": settings.max_output_tokens,
            "history_messages": len(request.history),
            "rag_enabled": settings.rag_enabled,
            "rag_chunks": len(retrieval_result.chunks) if retrieval_result else 0,
            "rag_metadata_assets": len(retrieval_result.metadata_assets) if retrieval_result else 0,
            "rag_sources": len(retrieval_result.sources) if retrieval_result else 0,
            "rag_entities": sorted(retrieval_result.detected_entities) if retrieval_result else [],
            "rag_resources": sorted(retrieval_result.detected_resources)
            if retrieval_result
            else [],
            "rag_listing_question": retrieval_result.listing_question
            if retrieval_result
            else False,
            "rag_context_document_chunks": retrieval_result.context_document_chunks
            if retrieval_result
            else 0,
            "rag_best_distance": retrieval_result.best_distance if retrieval_result else None,
            "rag_max_distance": settings.rag_max_distance,
            "rag_discarded_chunks": retrieval_result.discarded_chunks if retrieval_result else 0,
            "rag_query_variants": retrieval_result.query_variants if retrieval_result else 0,
            "rag_history_context_used": retrieval_result.history_context_used
            if retrieval_result
            else False,
        },
    )

    return ChatResponse(
        answer=guarded_response.answer,
        sources=retrieval_result.sources if retrieval_result else [],
        usage=result.usage,
        cost_status=settings.cost_status,
        rag_enabled=settings.rag_enabled,
        request_id=request_id,
    )


def create_app() -> FastAPI:
    return app
