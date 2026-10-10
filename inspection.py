"""Shared coordination for metadata extraction and privacy analysis."""

import mimetypes
from pathlib import Path

import metadata_extractor
from privacy_analyzer import analyze_privacy


def inspect_file(file_path: Path) -> dict:
    """Return file details, original metadata and privacy findings.

    Unsupported types raise ValueError; filesystem and extractor errors
    propagate to the caller. No JSON conversion is performed.
    """
    file_path = Path(file_path)
    size_bytes = file_path.stat().st_size
    mime_type, _ = mimetypes.guess_type(file_path)
    extractors = {
        "application/pdf": metadata_extractor.extract_pdf_metadata,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": metadata_extractor.extract_docx_metadata,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": metadata_extractor.extract_xlsx_metadata,
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": metadata_extractor.extract_pptx_metadata,
        "audio/mpeg": metadata_extractor.extract_mp3_metadata,
        "video/mp4": metadata_extractor.extract_video_metadata,
        "video/quicktime": metadata_extractor.extract_video_metadata,
    }
    if mime_type and mime_type.startswith("image/"):
        extractor = metadata_extractor.extract_image_metadata
    else:
        extractor = extractors.get(mime_type)
    if extractor is None:
        raise ValueError(f"Unsupported file type: {mime_type or file_path.suffix}")
    metadata = extractor(file_path)
    return {
        "file": {
            "name": file_path.name,
            "extension": file_path.suffix,
            "size_bytes": size_bytes,
            "mime_type": mime_type,
        },
        "metadata": metadata,
        "findings": analyze_privacy(metadata),
    }
