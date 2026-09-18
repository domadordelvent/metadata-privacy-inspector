import mimetypes
import sys
from pathlib import Path
from metadata_extractor import extract_image_metadata
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