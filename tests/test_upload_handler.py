from io import BytesIO
from pathlib import Path
import struct
from zipfile import ZipFile, ZIP_DEFLATED

import pytest
from PIL import Image
from docx import Document
from openpyxl import Workbook
from pptx import Presentation
from pypdf import PdfWriter

import upload_handler as uploads
from inspection import inspect_file


def image_bytes(format='PNG', size=(10, 10)):
    output = BytesIO()
    Image.new('RGB', size).save(output, format=format)
    return output.getvalue()


def test_private_storage_and_cleanup():
    source = BytesIO(image_bytes())
    with uploads.staged_upload(source, '../../secret.png') as path:
        directory = path.parent
        assert path.name == 'upload.png'
        assert directory.stat().st_mode & 0o777 == 0o700
        assert path.stat().st_mode & 0o777 == 0o600
        assert inspect_file(path)['metadata']['width'] == 10
    assert not directory.exists()
    assert not source.closed


def test_cleanup_after_processing_error():
    with pytest.raises(RuntimeError):
        with uploads.staged_upload(BytesIO(image_bytes()), 'image.png') as path:
            directory = path.parent
            raise RuntimeError('processor failed')
    assert not directory.exists()


@pytest.fixture
def temporary_root(monkeypatch, tmp_path):
    original = uploads.TemporaryDirectory
    monkeypatch.setattr(uploads, 'TemporaryDirectory', lambda **kw: original(dir=tmp_path, **kw))
    return tmp_path


@pytest.mark.parametrize('name, content', [
    ('image.png', b''), ('image.png', b'fake'),
    ('image.jpg', image_bytes()), ('document.pdf', b'%PDF-fake'),
    ('document.docx', b'not a zip'), ('audio.mp3', b'ID3fake'),
    ('video.mp4', b'fake'), ('video.mov', b'fake'),
    ('unknown.txt', b'file'), ('image.svg', b'<svg/>'),
    ('bad\x00.png', b'file'),
])
def test_rejects_invalid_uploads_and_cleans(temporary_root, name, content):
    with pytest.raises(uploads.UploadValidationError):
        with uploads.staged_upload(BytesIO(content), name):
            pytest.fail('Invalid upload accepted')
    assert list(temporary_root.iterdir()) == []


def test_file_limit_boundaries(monkeypatch, temporary_root):
    data = image_bytes()
    monkeypatch.setattr(uploads, 'MAX_FILE_BYTES', len(data))
    with uploads.staged_upload(BytesIO(data), 'image.png'):
        pass
    with pytest.raises(uploads.UploadTooLargeError):
        with uploads.staged_upload(BytesIO(data + b'x'), 'image.png'):
            pass
    assert list(temporary_root.iterdir()) == []


def test_real_twenty_mib_limit(temporary_root):
    assert uploads.MAX_FILE_BYTES == 20 * 1024 * 1024
    with pytest.raises(uploads.UploadTooLargeError):
        with uploads.staged_upload(BytesIO(b'x' * (uploads.MAX_FILE_BYTES + 1)), 'image.png'):
            pass
    assert list(temporary_root.iterdir()) == []


def test_read_error_cleans(temporary_root):
    class BrokenStream:
        def read(self, size):
            raise OSError('read failed')
    with pytest.raises(OSError):
        with uploads.staged_upload(BrokenStream(), 'image.png'):
            pass
    assert list(temporary_root.iterdir()) == []


def test_pixel_limit(monkeypatch):
    monkeypatch.setattr(uploads, 'MAX_IMAGE_PIXELS', 99)
    with pytest.raises(uploads.UploadValidationError, match='pixel'):
        with uploads.staged_upload(BytesIO(image_bytes()), 'image.png'):
            pass


def test_animated_image_limits(monkeypatch):
    output = BytesIO()
    frames = [Image.new('RGB', (10, 10), color=c) for c in ('red', 'blue')]
    frames[0].save(output, format='GIF', save_all=True, append_images=frames[1:])
    monkeypatch.setattr(uploads, 'MAX_IMAGE_FRAMES', 1)
    with pytest.raises(uploads.UploadValidationError, match='frame'):
        with uploads.staged_upload(BytesIO(output.getvalue()), 'image.gif'):
            pass
    monkeypatch.setattr(uploads, 'MAX_IMAGE_FRAMES', 100)
    monkeypatch.setattr(uploads, 'MAX_IMAGE_PIXELS', 150)
    with pytest.raises(uploads.UploadValidationError, match='aggregate'):
        with uploads.staged_upload(BytesIO(output.getvalue()), 'image.gif'):
            pass


@pytest.mark.parametrize('suffix, factory', [('.docx', Document), ('.xlsx', Workbook), ('.pptx', Presentation)])
def test_real_office_formats(suffix, factory):
    output = BytesIO()
    factory().save(output)
    with uploads.staged_upload(BytesIO(output.getvalue()), 'sample' + suffix) as path:
        assert isinstance(inspect_file(path)['metadata'], dict)
    wrong = '.xlsx' if suffix != '.xlsx' else '.docx'
    with pytest.raises(uploads.UploadValidationError):
        with uploads.staged_upload(BytesIO(output.getvalue()), 'sample' + wrong):
            pass


def office_archive(extra=None):
    output = BytesIO()
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        for name in ('[Content_Types].xml', '_rels/.rels', 'word/document.xml'):
            archive.writestr(name, '<xml/>')
        for name, value in (extra or {}).items():
            archive.writestr(name, value)
    return output.getvalue()


@pytest.mark.parametrize('extra', [{'bomb': b'x' * 100000}, {'../escape': b'x'}])
def test_office_bomb_and_unsafe_names(extra):
    with pytest.raises(uploads.UploadValidationError):
        with uploads.staged_upload(BytesIO(office_archive(extra)), 'sample.docx'):
            pass


@pytest.mark.parametrize('constant, value', [
    ('MAX_OFFICE_MEMBERS', 2), ('MAX_OFFICE_BYTES', 10), ('MAX_OFFICE_MEMBER_BYTES', 4),
])
def test_office_limits(monkeypatch, constant, value):
    monkeypatch.setattr(uploads, constant, value)
    with pytest.raises(uploads.UploadValidationError):
        with uploads.staged_upload(BytesIO(office_archive()), 'sample.docx'):
            pass


def test_office_crc_corruption():
    output = BytesIO()
    with ZipFile(output, 'w') as archive:
        for name in ('[Content_Types].xml', '_rels/.rels', 'word/document.xml'):
            archive.writestr(name, 'unique-content')
    corrupt = output.getvalue().replace(b'unique-content', b'broken-content', 1)
    with pytest.raises(uploads.UploadValidationError):
        with uploads.staged_upload(BytesIO(corrupt), 'sample.docx'):
            pass


def test_valid_pdf():
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(output)
    with uploads.staged_upload(BytesIO(output.getvalue()), 'sample.pdf'):
        pass


def box(kind, payload=b''):
    return struct.pack('>I4s', len(payload) + 8, kind) + payload


@pytest.mark.parametrize('suffix, brand', [('.mp4', b'isom'), ('.mov', b'qt  ')])
def test_video_container_consistency(suffix, brand):
    data = box(b'ftyp', brand + b'\0' * 4) + box(b'moov')
    with uploads.staged_upload(BytesIO(data), 'sample' + suffix):
        pass
    other = '.mov' if suffix == '.mp4' else '.mp4'
    with pytest.raises(uploads.UploadValidationError):
        with uploads.staged_upload(BytesIO(data), 'sample' + other):
            pass


def test_truncated_video_box():
    with pytest.raises(uploads.UploadValidationError):
        with uploads.staged_upload(BytesIO(struct.pack('>I4s', 1000, b'ftyp')), 'sample.mp4'):
            pass


def test_valid_mp3_frames():
    # MPEG1 layer III, 128 kbps, 44.1 kHz, padded with silence bytes.
    frame = b'\xff\xfb\x90\x00' + b'\0' * 413
    with uploads.staged_upload(BytesIO(frame * 10), 'sample.mp3'):
        pass
