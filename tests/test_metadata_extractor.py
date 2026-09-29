from pypdf import PdfWriter

from openpyxl import Workbook

import pytest
from pypdf.errors import PdfReadError




from metadata_extractor import (
    extract_pdf_metadata,
    extract_xlsx_metadata,
    extract_pptx_metadata,
    extract_mp3_metadata,
    extract_video_metadata,
)

from pptx import Presentation

def test_extracts_pdf_metadata(tmp_path):
    file_path = tmp_path / "test.pdf"

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.add_metadata({
        "/Author": "Test Author",
        "/Creator": "Test Creator",
        "/Producer": "Test Producer",
    })

    with open(file_path, "wb") as file:
        writer.write(file)

    metadata = extract_pdf_metadata(file_path)

    assert metadata["Author"] == "Test Author"
    assert metadata["Creator"] == "Test Creator"
    assert metadata["Producer"] == "Test Producer"

def test_extracts_pdf_without_custom_metadata(tmp_path):
    file_path = tmp_path / "empty_metadata.pdf"

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)

    with open(file_path, "wb") as file:
        writer.write(file)

    metadata = extract_pdf_metadata(file_path)

    assert isinstance(metadata, dict)

def test_rejects_invalid_pdf(tmp_path):
    file_path = tmp_path / "invalid.pdf"
    file_path.write_bytes(b"This is not a PDF")

    with pytest.raises(PdfReadError):
        extract_pdf_metadata(file_path)


def test_extracts_xlsx_metadata(tmp_path):
    file_path = tmp_path / "test.xlsx"

    workbook = Workbook()
    workbook.properties.title = "Test XLSX"
    workbook.properties.creator = "Test Author"
    workbook.properties.description = "Test Comments"
    workbook.save(file_path)

    metadata = extract_xlsx_metadata(file_path)

    assert metadata["Title"] == "Test XLSX"
    assert metadata["Author"] == "Test Author"
    assert metadata["Comments"] == "Test Comments"

def test_extracts_pptx_metadata(tmp_path):
    file_path = tmp_path / "test.pptx"

    presentation = Presentation()
    properties = presentation.core_properties

    properties.title = "Test PPTX"
    properties.author = "Test Author"
    properties.comments = "Test Comments"

    presentation.save(file_path)

    metadata = extract_pptx_metadata(file_path)

    assert metadata["Title"] == "Test PPTX"
    assert metadata["Author"] == "Test Author"
    assert metadata["Comments"] == "Test Comments"

def test_extracts_mp3_metadata(monkeypatch, tmp_path):
    class FakeInfo:
        length = 123.4
        bitrate = 128000
        sample_rate = 44100

    class FakeAudio:
        tags = {
            "TIT2": "Test MP3",
            "TPE1": "Test Artist",
            "TALB": "Test Album",
            "TXXX:comment": "Private comment",
            "TSSE": "Test Encoder",
        }
        info = FakeInfo()

    monkeypatch.setattr(
        "metadata_extractor.MP3",
        lambda file_path: FakeAudio(),
    )

    metadata = extract_mp3_metadata(tmp_path / "test.mp3")

    assert metadata["Title"] == "Test MP3"
    assert metadata["Artist"] == "Test Artist"
    assert metadata["Album"] == "Test Album"
    assert metadata["Comment"] == "Private comment"
    assert metadata["Encoder"] == "Test Encoder"
    assert metadata["Duration"] == 123.4
    assert metadata["Bitrate"] == 128000
    assert metadata["SampleRate"] == 44100


def test_extracts_video_metadata(monkeypatch, tmp_path):
    class FakeResult:
        stdout = """
        {
            "format": {
                "duration": "10.000000",
                "bit_rate": "500000",
                "tags": {
                    "title": "Test Video",
                    "artist": "Test Artist",
                    "comment": "Private comment",
                    "creation_time": "2026-09-30T20:00:00Z",
                    "location": "+41.3874+002.1686/"
                }
            }
        }
        """

    monkeypatch.setattr(
        "metadata_extractor.subprocess.run",
        lambda *args, **kwargs: FakeResult(),
    )

    metadata = extract_video_metadata(tmp_path / "test.mp4")

    assert metadata["Title"] == "Test Video"
    assert metadata["Artist"] == "Test Artist"
    assert metadata["Comment"] == "Private comment"
    assert metadata["CreationDate"] == "2026-09-30T20:00:00Z"
    assert metadata["Location"] == "+41.3874+002.1686/"
    assert metadata["Duration"] == "10.000000"
    assert metadata["Bitrate"] == "500000"