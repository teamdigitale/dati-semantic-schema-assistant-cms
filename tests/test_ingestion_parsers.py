from pathlib import Path
from types import SimpleNamespace

import pytest

from schema_assistant.ingestion.discovery import SourceFile
from schema_assistant.ingestion.parsers import AssetParser


def test_parse_yaml_asset(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    source_path = tmp_path / "schema.yaml"
    source_path.write_text("info:\n  title: Test\n", encoding="utf-8")

    parsed = AssetParser().parse(_source(source_path, "yaml_schemas"))

    assert "Test" in parsed.content
    assert parsed.processed_payload["format"] == "yaml"


def test_parse_csv_asset(tmp_path: Path) -> None:
    source_path = tmp_path / "date.csv"
    source_path.write_text("name,date\nA,2026-01-01\n", encoding="utf-8")

    parsed = AssetParser().parse(_source(source_path, "dates_collection"))

    assert "2026-01-01" in parsed.content
    assert parsed.processed_payload["row_count"] == 1


def test_parse_ttl_asset(tmp_path: Path) -> None:
    pytest.importorskip("rdflib")
    source_path = tmp_path / "vocab.ttl"
    source_path.write_text(
        """
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix ex: <https://example.org/> .

ex:item a skos:Concept ;
  skos:prefLabel "Elemento"@it ;
  skos:definition "Definizione di test"@it .
""".strip(),
        encoding="utf-8",
    )

    parsed = AssetParser().parse(_source(source_path, "vocabularies"))

    assert "Elemento" in parsed.content
    assert parsed.processed_payload["triple_count"] >= 3


def test_parse_pdf_tracks_text_coverage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_path = tmp_path / "guide.pdf"
    source_path.write_bytes(b"%PDF-1.4")
    monkeypatch.setitem(
        __import__("sys").modules,
        "pdfplumber",
        SimpleNamespace(open=lambda _path: _FakePdf(["Prima pagina", "", "Terza pagina"])),
    )

    parsed = AssetParser().parse(_source(source_path, "context_documents"))

    assert "Pagina 1" in parsed.content
    assert "Pagina 3" in parsed.content
    assert parsed.processed_payload["page_count"] == 3
    assert parsed.processed_payload["text_page_count"] == 2
    assert parsed.processed_payload["extracted_chars"] > 0


def test_parse_pdf_rejects_documents_without_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "scan.pdf"
    source_path.write_bytes(b"%PDF-1.4")
    monkeypatch.setitem(
        __import__("sys").modules,
        "pdfplumber",
        SimpleNamespace(open=lambda _path: _FakePdf(["", ""])),
    )

    with pytest.raises(ValueError, match="require OCR"):
        AssetParser().parse(_source(source_path, "context_documents"))


def _source(path: Path, resource_id: str) -> SourceFile:
    return SourceFile(
        entity_id="istat",
        resource_id=resource_id,  # type: ignore[arg-type]
        path=path,
        relative_path=path.name,
        source_uri=f"file://{path.name}",
    )


class _FakePage:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text


class _FakePdf:
    def __init__(self, page_texts: list[str]) -> None:
        self.pages = [_FakePage(text) for text in page_texts]

    def __enter__(self) -> "_FakePdf":
        return self

    def __exit__(self, *_args: object) -> None:
        return None
