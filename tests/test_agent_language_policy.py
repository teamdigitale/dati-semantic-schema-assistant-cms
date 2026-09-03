from schema_assistant.agent.language_policy import detect_language


def test_detects_supported_languages() -> None:
    examples = {
        "Quali ontologie sono disponibili nel catalogo?": "it",
        "What ontologies are available in the Catalogue?": "en",
        "Quelles ontologies sont disponibles dans le Catalogue ?": "fr",
        "¿Cuáles ontologías están disponibles en el Catálogo?": "es",
        "Welche Ontologien sind im Katalog verfügbar?": "de",
    }

    for message, expected_language in examples.items():
        assert detect_language(message) == expected_language


def test_returns_none_for_ambiguous_technical_text() -> None:
    assert detect_language("SKOS ATECO RDF 47.11") is None
