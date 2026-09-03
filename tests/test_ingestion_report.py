import pytest


def test_ingestion_report_tracks_skipped_sources() -> None:
    pytest.importorskip("pydantic")
    from schema_assistant.ingestion.report import IngestionReport

    report = IngestionReport()

    report.mark_skipped(entity_id="istat", resource_id="vocabularies", chunks=42)

    assert report.files_skipped == 1
    assert report.by_entity["istat"]["files_skipped"] == 1
    assert report.by_entity["istat"]["vocabularies_skipped_chunks"] == 42
