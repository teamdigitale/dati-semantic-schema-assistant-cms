from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from schema_assistant.agent.language_policy import (
    detect_language,
    language_tokens,
)
from schema_assistant.agent.static_answers import SECURITY_BOUNDARY_ANSWERS


@dataclass(frozen=True)
class GuardedResponse:
    answer: str
    intervened: bool = False
    reason: str | None = None
    language_mismatch_observed: bool = False


def enforce_response_policy(
    answer: str,
    *,
    system_instruction: str,
    user_message: str = "",
) -> GuardedResponse:
    expected_language = detect_language(user_message) or "it"
    if _leaks_system_instruction(answer, system_instruction):
        return GuardedResponse(
            answer=SECURITY_BOUNDARY_ANSWERS[expected_language],
            intervened=True,
            reason="system_instruction_disclosure",
        )

    return GuardedResponse(
        answer=answer,
        language_mismatch_observed=_has_language_mismatch(answer, user_message),
    )


def _leaks_system_instruction(answer: str, system_instruction: str) -> bool:
    normalized_answer = _normalize_words(answer)
    normalized_instruction = _normalize_words(system_instruction)
    if not normalized_answer or not normalized_instruction:
        return False

    sensitive_markers = {
        "contenuti non fidati e prompt injection",
        "queste istruzioni di sistema hanno priorita",
        "non rivelare ripetere trascrivere riassumere tradurre o ricostruire",
        "eventuali istruzioni nascoste",
    }
    if any(marker in normalized_answer for marker in sensitive_markers):
        return True

    instruction_tokens = normalized_instruction.split()
    answer_tokens = normalized_answer.split()
    ngram_size = 10
    if len(answer_tokens) < ngram_size:
        return False

    instruction_ngrams = {
        tuple(instruction_tokens[index : index + ngram_size])
        for index in range(len(instruction_tokens) - ngram_size + 1)
    }
    matching_ngrams = sum(
        tuple(answer_tokens[index : index + ngram_size]) in instruction_ngrams
        for index in range(len(answer_tokens) - ngram_size + 1)
    )
    return matching_ngrams >= 2


def _has_language_mismatch(answer: str, user_message: str) -> bool:
    if _is_translation_request(user_message) or len(language_tokens(answer)) < 8:
        return False

    expected_language = detect_language(user_message)
    answer_language = detect_language(answer)
    return bool(expected_language and answer_language and expected_language != answer_language)


def _is_translation_request(user_message: str) -> bool:
    translation_markers = {
        "traduci",
        "tradurre",
        "traduce",
        "traducir",
        "traduire",
        "translate",
        "translation",
        "ubersetze",
        "ubersetzen",
    }
    return bool(set(language_tokens(user_message)) & translation_markers)


def _normalize_words(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower())
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(re.findall(r"\w+", ascii_value))
