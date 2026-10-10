from datetime import datetime

import pytest
from pypdf import PdfWriter

import inspection


@pytest.mark.parametrize("suffix, extractor", [
    (".jpg", "extract_image_metadata"),
    (".png", "extract_image_metadata"),
    (".pdf", "extract_pdf_metadata"),
    (".docx", "extract_docx_metadata"),
    (".xlsx", "extract_xlsx_metadata"),
    (".pptx", "extract_pptx_metadata"),
    (".mp3", "extract_mp3_metadata"),
    (".mp4", "extract_video_metadata"),
    (".mov", "extract_video_metadata"),
])
def test_routes_to_existing_extractor(monkeypatch, tmp_path, suffix, extractor):
    path = tmp_path / ("sample" + suffix)
    path.write_bytes(b"sample")
    metadata = {"Author": "Test Author", "CreationDate": datetime(2026, 1, 1)}
    calls = []

    def extract(received_path):
        calls.append(received_path)
        return metadata

    def unexpected(received_path):
        pytest.fail("Wrong extractor selected")

    for name in (
        "extract_image_metadata", "extract_pdf_metadata", "extract_docx_metadata",
        "extract_xlsx_metadata", "extract_pptx_metadata", "extract_mp3_metadata",
        "extract_video_metadata",
    ):
        monkeypatch.setattr(inspection.metadata_extractor, name, unexpected)
    monkeypatch.setattr(inspection.metadata_extractor, extractor, extract)

    result = inspection.inspect_file(path)

    assert calls == [path]
    assert result["file"] == {
        "name": path.name, "extension": suffix, "size_bytes": 6,
        "mime_type": inspection.mimetypes.guess_type(path)[0],
    }
    assert result["metadata"] is metadata
    assert result["findings"] == inspection.analyze_privacy(metadata)
    assert result["findings"][1]["value"] is metadata["CreationDate"]


def test_inspects_real_pdf(tmp_path):
    path = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.add_metadata({"/Author": "Test Author"})
    with path.open("wb") as output:
        writer.write(output)
    result = inspection.inspect_file(path)
    assert result["metadata"]["Author"] == "Test Author"
    assert any(f["field"] == "Author" for f in result["findings"])


def test_empty_metadata_has_no_findings(monkeypatch, tmp_path):
    path = tmp_path / "sample.pdf"
    path.touch()
    monkeypatch.setattr(inspection.metadata_extractor, "extract_pdf_metadata", lambda p: {})
    result = inspection.inspect_file(path)
    assert result["metadata"] == {}
    assert result["findings"] == []


def test_rejects_unsupported_format(tmp_path):
    path = tmp_path / "sample.txt"
    path.touch()
    with pytest.raises(ValueError, match="Unsupported file type"):
        inspection.inspect_file(path)


def test_missing_file():
    with pytest.raises(FileNotFoundError):
        inspection.inspect_file("/nonexistent/metadata-inspector/sample.pdf")


def test_extractor_error_propagates(monkeypatch, tmp_path):
    path = tmp_path / "sample.pdf"
    path.touch()
    error = RuntimeError("Extraction failed")

    def extract(path):
        raise error

    monkeypatch.setattr(inspection.metadata_extractor, "extract_pdf_metadata", extract)
    with pytest.raises(RuntimeError) as caught:
        inspection.inspect_file(path)
    assert caught.value is error
