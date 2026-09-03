from fastapi import HTTPException, status

from schema_assistant.agent.config import AgentSettings
from schema_assistant.agent.models import ChatMessage, ChatRequest


def validate_chat_request(request: ChatRequest, settings: AgentSettings) -> None:
    if settings.cost_status == "blocked":
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Il servizio e temporaneamente limitato per controllo costi.",
        )

    if len(request.message) > settings.max_input_chars:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Messaggio troppo lungo. Limite: {settings.max_input_chars} caratteri.",
        )

    if len(request.history) > settings.max_history_messages:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Cronologia troppo lunga. Limite: {settings.max_history_messages} messaggi.",
        )

    for item in request.history:
        _validate_history_item(item, settings)


def _validate_history_item(item: ChatMessage, settings: AgentSettings) -> None:
    if len(item.content) > settings.max_history_message_chars:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                "Un messaggio in cronologia supera il limite di "
                f"{settings.max_history_message_chars} caratteri."
            ),
        )
