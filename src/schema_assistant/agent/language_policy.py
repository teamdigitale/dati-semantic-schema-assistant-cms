from __future__ import annotations

import re
import unicodedata
from typing import Literal

LanguageCode = Literal["it", "en", "fr", "es", "de"]

LANGUAGE_MARKERS: dict[LanguageCode, set[str]] = {
    "it": {
        "che",
        "chi",
        "come",
        "della",
        "delle",
        "disponibili",
        "italiano",
        "istruzioni",
        "precedenti",
        "quale",
        "quali",
        "rispondi",
        "sistema",
        "sono",
        "tutto",
    },
    "en": {
        "answer",
        "are",
        "available",
        "english",
        "how",
        "instructions",
        "internal",
        "previous",
        "repeat",
        "reveal",
        "system",
        "the",
        "what",
        "which",
        "who",
        "write",
    },
    "fr": {
        "comment",
        "disponibles",
        "francais",
        "internes",
        "les",
        "precedentes",
        "quel",
        "quelle",
        "quelles",
        "qui",
        "reponds",
        "sont",
        "systeme",
        "toutes",
        "vous",
    },
    "es": {
        "como",
        "cual",
        "cuales",
        "disponibles",
        "estan",
        "espanol",
        "instrucciones",
        "internas",
        "internos",
        "anteriores",
        "quien",
        "responde",
        "son",
        "sistema",
        "todas",
        "usted",
    },
    "de": {
        "antworte",
        "anweisungen",
        "deutsch",
        "interne",
        "sind",
        "system",
        "verfugbar",
        "vorherigen",
        "welche",
        "welcher",
        "wer",
        "wie",
    },
}


def detect_language(value: str) -> LanguageCode | None:
    tokens = _language_tokens(value)
    if not tokens:
        return None

    scores = {
        language: sum(token in markers for token in tokens)
        for language, markers in LANGUAGE_MARKERS.items()
    }
    highest_score = max(scores.values(), default=0)
    if highest_score == 0:
        return None

    winners = [language for language, score in scores.items() if score == highest_score]
    return winners[0] if len(winners) == 1 else None


def language_tokens(value: str) -> list[str]:
    return _language_tokens(value)


def _language_tokens(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", value.lower())
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.findall(r"\w+", ascii_value)
