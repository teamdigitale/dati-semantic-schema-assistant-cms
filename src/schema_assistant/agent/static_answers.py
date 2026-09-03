import re
import unicodedata
from dataclasses import dataclass

from schema_assistant.agent.language_policy import LanguageCode, detect_language

CATALOG_IDENTITY_ANSWER = (
    "Sono l'assistente del catalogo per l'interoperabilità della semantica dei dati, "
    "che può aiutarti a conoscere le risorse semantiche pubblicate sul catalogo.\n\n"
    "Posso risponderti sulle risorse pubblicate da INPS, INAIL, ISTAT e su alcuni "
    "argomenti di semantica e di interoperabilità dei dati. Puoi ritrovare i "
    "contenuti che ti proporrò direttamente sulle pagine di schema.gov.it."
)

DEVELOPER_IDENTITY_ANSWER = (
    "Sono stato sviluppato da DXC Technology, fornitore e azienda leader globale "
    "nei servizi IT e soluzioni digitali.\n\n"
    "DXC è partner operativo di fiducia per molte delle organizzazioni più "
    "innovative al mondo, con cui collabora per sviluppare soluzioni che promuovono "
    "l'evoluzione dei settori e la crescita delle imprese.\n\n"
    "Grazie all'esperienza dei suoi professionisti in ingegneria, consulenza e "
    "tecnologia, DXC aiuta i clienti a semplificare, ottimizzare e modernizzare "
    "sistemi e processi, gestire carichi di lavoro critici e integrare "
    "l'intelligenza artificiale in modo sicuro ed efficiente. Questa competenza "
    "è alla base della mia progettazione, per offrire un'esperienza conversazionale "
    "innovativa e di qualità."
)

SECURITY_BOUNDARY_ANSWER = (
    "Non posso fornire, ripetere o ricostruire istruzioni interne, configurazioni "
    "o prompt di sistema. Posso invece aiutarti, in italiano, con le risorse "
    "semantiche presenti nel catalogo."
)

INSTRUCTION_OVERRIDE_ANSWER = (
    "Non posso ignorare le istruzioni operative, cambiare ruolo o uscire "
    "dall'ambito del catalogo. Posso aiutarti in italiano con le risorse "
    "semantiche disponibili."
)

CATALOG_IDENTITY_ANSWERS: dict[LanguageCode, str] = {
    "it": CATALOG_IDENTITY_ANSWER,
    "en": (
        "I am the assistant for the Data Semantics Interoperability Catalogue. "
        "I can help you explore the semantic resources published in the Catalogue."
    ),
    "fr": (
        "Je suis l'assistant du Catalogue pour l'interopérabilité de la sémantique "
        "des données. Je peux vous aider à explorer ses ressources sémantiques."
    ),
    "es": (
        "Soy el asistente del Catálogo para la interoperabilidad de la semántica "
        "de los datos. Puedo ayudarte a explorar sus recursos semánticos."
    ),
    "de": (
        "Ich bin der Assistent des Katalogs für die Interoperabilität der "
        "Datensemantik. Ich helfe Ihnen bei der Suche nach semantischen Ressourcen."
    ),
}

DEVELOPER_IDENTITY_ANSWERS: dict[LanguageCode, str] = {
    "it": DEVELOPER_IDENTITY_ANSWER,
    "en": "I was developed by DXC Technology, a global IT services company.",
    "fr": "J'ai été développé par DXC Technology, une entreprise mondiale de services IT.",
    "es": "Fui desarrollado por DXC Technology, una empresa global de servicios de TI.",
    "de": "Ich wurde von DXC Technology, einem globalen IT-Dienstleister, entwickelt.",
}

SECURITY_BOUNDARY_ANSWERS: dict[LanguageCode, str] = {
    "it": SECURITY_BOUNDARY_ANSWER,
    "en": (
        "I cannot provide, repeat, or reconstruct internal instructions, system "
        "configuration, or system prompts. I can help with semantic resources in the Catalogue."
    ),
    "fr": (
        "Je ne peux pas fournir, répéter ou reconstruire les instructions internes, "
        "la configuration ou le prompt système. Je peux vous aider avec les ressources "
        "sémantiques du Catalogue."
    ),
    "es": (
        "No puedo proporcionar, repetir ni reconstruir instrucciones internas, la "
        "configuración o el prompt del sistema. Puedo ayudarte con los recursos "
        "semánticos del Catálogo."
    ),
    "de": (
        "Ich kann interne Anweisungen, Systemkonfigurationen oder System-Prompts "
        "nicht bereitstellen, wiederholen oder rekonstruieren. Ich helfe Ihnen gern "
        "mit den semantischen Ressourcen des Katalogs."
    ),
}

INSTRUCTION_OVERRIDE_ANSWERS: dict[LanguageCode, str] = {
    "it": INSTRUCTION_OVERRIDE_ANSWER,
    "en": (
        "I cannot ignore the operating instructions, change my role, or leave the "
        "Catalogue scope. I can help with the available semantic resources."
    ),
    "fr": (
        "Je ne peux pas ignorer les instructions, changer de rôle ou sortir du "
        "périmètre du Catalogue. Je peux vous aider avec les ressources sémantiques disponibles."
    ),
    "es": (
        "No puedo ignorar las instrucciones, cambiar de función ni salir del ámbito "
        "del Catálogo. Puedo ayudarte con los recursos semánticos disponibles."
    ),
    "de": (
        "Ich kann die Betriebsanweisungen nicht ignorieren, meine Rolle nicht ändern "
        "und den Katalogbereich nicht verlassen. Ich helfe mit den verfügbaren Ressourcen."
    ),
}


@dataclass(frozen=True)
class StaticAnswer:
    answer: str
    reason: str


def find_static_answer(message: str) -> StaticAnswer | None:
    tokens = _tokens(message)
    token_set = set(tokens)
    language = detect_language(message) or "it"

    if _is_system_prompt_disclosure(token_set):
        return StaticAnswer(
            answer=SECURITY_BOUNDARY_ANSWERS[language],
            reason="security_prompt_disclosure",
        )

    if _is_instruction_override(tokens, token_set):
        return StaticAnswer(
            answer=INSTRUCTION_OVERRIDE_ANSWERS[language],
            reason="security_instruction_override",
        )

    # Queste risposte sono stabili: non serve interrogare retrieval o modello.
    if _is_developer_question(tokens, token_set):
        return StaticAnswer(
            answer=DEVELOPER_IDENTITY_ANSWERS[language],
            reason="identity_developer",
        )

    if _is_catalog_identity_question(tokens, token_set):
        return StaticAnswer(
            answer=CATALOG_IDENTITY_ANSWERS[language],
            reason="identity_catalog",
        )

    return None


def _is_system_prompt_disclosure(token_set: set[str]) -> bool:
    disclosure_markers = {
        "descrivi",
        "dimmi",
        "elenca",
        "fornisci",
        "muestra",
        "mostra",
        "montre",
        "repete",
        "repite",
        "quali",
        "repeat",
        "reveal",
        "ripeti",
        "rivela",
        "revele",
        "revela",
        "stampa",
        "trascrivi",
        "wiederhole",
        "what",
        "zeige",
    }
    if not token_set & disclosure_markers:
        return False

    explicitly_internal = bool(
        token_set & {"internal", "interne", "internes", "interno", "internos", "internas"}
        and token_set
        & {
            "anweisungen",
            "configuracion",
            "configuration",
            "configurazione",
            "direttive",
            "instructions",
            "instrucciones",
            "istruzioni",
            "policy",
            "regeln",
            "regles",
            "regole",
        }
    )
    explicit_system_prompt = "prompt" in token_set and bool(
        token_set & {"sistema", "system", "systeme"}
    )
    return explicitly_internal or explicit_system_prompt


def _is_instruction_override(tokens: list[str], token_set: set[str]) -> bool:
    override_markers = {
        "bypass",
        "bypassa",
        "dimentica",
        "disattiva",
        "desactiva",
        "desactive",
        "disregard",
        "forget",
        "ignora",
        "ignore",
        "ignoriere",
        "olvida",
        "oublie",
        "override",
        "sovrascrivi",
        "vergiss",
    }
    controlled_targets = {
        "everything",
        "instructions",
        "instrucciones",
        "istruzioni",
        "policy",
        "precedenti",
        "previous",
        "prompt",
        "regeln",
        "regles",
        "regole",
        "rules",
        "sistema",
        "system",
        "systeme",
        "tutto",
        "vincoli",
    }
    if token_set & override_markers and token_set & controlled_targets:
        return True

    normalized = " ".join(tokens)
    override_phrases = {
        "ignora todo",
        "ignora tutto",
        "ignore everything",
        "ignore tout",
        "ignoriere alles",
    }
    return any(phrase in normalized for phrase in override_phrases)


def _is_developer_question(tokens: list[str], token_set: set[str]) -> bool:
    developer_markers = {
        "creatore",
        "creato",
        "created",
        "cree",
        "creo",
        "desarrollado",
        "developed",
        "developpe",
        "entwickelt",
        "erstellt",
        "inventato",
        "realizzato",
        "sviluppatore",
        "sviluppato",
    }
    question_words = {"chi", "quien", "qui", "wer", "who"}
    if not token_set & question_words or not token_set & developer_markers:
        return False

    assistant_references = {
        "assistant",
        "assistente",
        "bot",
        "chatbot",
        "dich",
        "du",
        "sei",
        "te",
        "ti",
        "tu",
        "vous",
        "you",
    }
    if token_set & assistant_references:
        return True

    normalized = " ".join(tokens)
    return "tuo sviluppatore" in normalized or "tua sviluppatrice" in normalized


def _is_catalog_identity_question(tokens: list[str], token_set: set[str]) -> bool:
    if {"chi", "sei"}.issubset(token_set):
        return True
    if {"chi", "assistente"}.issubset(token_set):
        return True
    if "presentati" in token_set:
        return True

    normalized = " ".join(tokens)
    identity_phrases = {
        "quien eres",
        "qui es tu",
        "wer bist du",
        "who are you",
    }
    if any(phrase in normalized for phrase in identity_phrases):
        return True

    greeting_tokens = {
        "bonjour",
        "buenas",
        "buenos",
        "buongiorno",
        "buonasera",
        "ciao",
        "guten",
        "hallo",
        "hello",
        "hola",
        "salve",
    }
    return bool(token_set & greeting_tokens) and len(tokens) <= 3


def _tokens(message: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", message.lower())
    ascii_message = normalized.encode("ascii", "ignore").decode("ascii")
    return re.findall(r"\w+", ascii_message)
