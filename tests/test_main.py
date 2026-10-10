import subprocess
import sys
from pathlib import Path

from pypdf import PdfWriter


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_import_does_not_execute_cli():
    result = subprocess.run(
        [sys.executable, "-c", "import main; assert callable(main.main)"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, check=True,
    )
    assert result.stdout == ""
    assert result.stderr == ""


def test_cli_preserves_output(tmp_path):
    path = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.add_metadata({"/Author": "Test Author", "/Producer": "Test Producer"})
    with path.open("wb") as output:
        writer.write(output)

    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "main.py"), str(path)],
        cwd=PROJECT_ROOT, capture_output=True, text=True, check=True,
    )
    assert result.stdout == (
        "Name: sample.pdf\n"
        "Extension: .pdf\n"
        f"Size: {path.stat().st_size / 1024:.1f} KB\n"
        "MIME type: application/pdf\n"
        "\nMetadata:\n"
        "Producer: Test Producer\n"
        "Author: Test Author\n"
        "\nPrivacy findings:\n"
        "- Author: Test Author (Document author)\n"
        "- Producer: Test Producer (Software used to produce the document)\n"
    )
    assert result.stderr == ""
