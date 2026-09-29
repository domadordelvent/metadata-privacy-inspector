import mimetypes
import sys
from pathlib import Path
from metadata_extractor import (
    extract_image_metadata, 
    extract_pdf_metadata, 
    extract_docx_metadata, 
    extract_xlsx_metadata,
    extract_pptx_metadata,
    extract_mp3_metadata,
    extract_video_metadata
)
from privacy_analyzer import analyze_privacy


file_path = Path(sys.argv[1])

print(f"Name: {file_path.name}")
print(f"Extension: {file_path.suffix}")

size_kb = file_path.stat().st_size / 1024
print(f"Size: {size_kb:.1f} KB")

mime_type, _ = mimetypes.guess_type(file_path)
print(f"MIME type: {mime_type}")

if mime_type and mime_type.startswith("image/"):
    metadata = extract_image_metadata(file_path)

elif mime_type == "application/pdf":
    metadata = extract_pdf_metadata(file_path)

elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
    metadata = extract_docx_metadata(file_path)

elif mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
    metadata = extract_xlsx_metadata(file_path)

elif mime_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
    metadata = extract_pptx_metadata(file_path)

elif mime_type == "audio/mpeg":
    metadata = extract_mp3_metadata(file_path)

elif mime_type in ("video/mp4", "video/quicktime"):
    metadata = extract_video_metadata(file_path)

print("\nMetadata:")
for key, value in metadata.items():
    print(f"{key}: {value}")

findings = analyze_privacy(metadata)

if findings:
    print("\nPrivacy findings:")

    for finding in findings:
        print(
            f"- {finding['field']}: {finding['value']} "
            f"({finding['description']})"
        )