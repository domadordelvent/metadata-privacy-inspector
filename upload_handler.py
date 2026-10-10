"""Bounded upload staging, independent of HTTP and extraction logic."""

from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import BinaryIO, Iterator
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile
import struct

from PIL import Image, UnidentifiedImageError
from mutagen.mp3 import MP3, HeaderNotFoundError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_FILE_BYTES = 20 * 1024 * 1024
CHUNK_BYTES = 64 * 1024
MAX_IMAGE_PIXELS = 25_000_000
MAX_IMAGE_FRAMES = 100
MAX_OFFICE_BYTES = 100 * 1024 * 1024
MAX_OFFICE_MEMBER_BYTES = 20 * 1024 * 1024
MAX_OFFICE_MEMBERS = 2000
MAX_COMPRESSION_RATIO = 100

# Only raster formats already handled by Pillow's existing extractor.
IMAGE_FORMATS = {
    '.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG', '.gif': 'GIF',
    '.webp': 'WEBP', '.bmp': 'BMP', '.tif': 'TIFF', '.tiff': 'TIFF',
    '.ico': 'ICO', '.ppm': 'PPM', '.pgm': 'PPM', '.pbm': 'PPM',
}
OFFICE_PARTS = {
    '.docx': 'word/document.xml', '.xlsx': 'xl/workbook.xml',
    '.pptx': 'ppt/presentation.xml',
}
SUPPORTED_EXTENSIONS = frozenset(IMAGE_FORMATS) | frozenset(OFFICE_PARTS) | {
    '.pdf', '.mp3', '.mp4', '.mov',
}


class UploadValidationError(ValueError):
    """Upload is empty, unsupported, malformed or exceeds a safety limit."""


class UploadTooLargeError(UploadValidationError):
    """Upload exceeds the file size limit."""


class UnsupportedUploadFormatError(UploadValidationError):
    """Upload format is not supported."""


def _validate_image(path: Path, suffix: str) -> None:
    with Image.open(path, formats=[IMAGE_FORMATS[suffix]]) as image:
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise UploadValidationError('Image exceeds pixel limit')
        frames = getattr(image, 'n_frames', 1)
        if frames > MAX_IMAGE_FRAMES:
            raise UploadValidationError('Image exceeds frame limit')
        total_pixels = 0
        for frame in range(frames):
            image.seek(frame)
            total_pixels += image.width * image.height
            if total_pixels > MAX_IMAGE_PIXELS:
                raise UploadValidationError('Image exceeds aggregate pixel limit')
    with Image.open(path, formats=[IMAGE_FORMATS[suffix]]) as image:
        image.verify()


def _validate_office(path: Path, suffix: str) -> None:
    with ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_OFFICE_MEMBERS:
            raise UploadValidationError('Office archive contains too many members')
        names = {entry.filename for entry in entries}
        if len(names) != len(entries):
            raise UploadValidationError('Duplicate Office archive members')
        if not {'[Content_Types].xml', '_rels/.rels', OFFICE_PARTS[suffix]} <= names:
            raise UploadValidationError('Office content does not match declared format')
        total = 0
        for entry in entries:
            name = PurePosixPath(entry.filename)
            if name.is_absolute() or '..' in name.parts or '\\' in entry.filename:
                raise UploadValidationError('Unsafe Office archive member')
            if entry.flag_bits & 1 or entry.compress_type not in (ZIP_STORED, ZIP_DEFLATED):
                raise UploadValidationError('Unsupported Office archive encoding')
            total += entry.file_size
            if (entry.file_size > MAX_OFFICE_MEMBER_BYTES or total > MAX_OFFICE_BYTES
                    or entry.file_size > max(entry.compress_size, 1) * MAX_COMPRESSION_RATIO):
                raise UploadValidationError('Office archive exceeds decompression limits')
        # Read bounded members to check actual decompression and CRC, never extract.
        actual_total = 0
        for entry in entries:
            actual_size = 0
            with archive.open(entry) as member:
                while chunk := member.read(CHUNK_BYTES):
                    actual_size += len(chunk)
                    actual_total += len(chunk)
                    if actual_size > MAX_OFFICE_MEMBER_BYTES or actual_total > MAX_OFFICE_BYTES:
                        raise UploadValidationError('Office archive exceeds decompression limits')


def _validate_video(path: Path, suffix: str) -> None:
    # Structural ISO BMFF/QuickTime check; full codec validation belongs to ffprobe.
    size = path.stat().st_size
    saw_format = False
    saw_movie = False
    with path.open('rb') as source:
        while source.tell() < size:
            offset = source.tell()
            header = source.read(8)
            if len(header) != 8:
                raise UploadValidationError('Truncated video container')
            box_size, kind = struct.unpack('>I4s', header)
            header_size = 8
            if box_size == 1:
                extended = source.read(8)
                if len(extended) != 8:
                    raise UploadValidationError('Truncated video container')
                box_size = struct.unpack('>Q', extended)[0]
                header_size = 16
            elif box_size == 0:
                box_size = size - offset
            if box_size < header_size or offset + box_size > size:
                raise UploadValidationError('Invalid video box size')
            if kind == b'ftyp':
                if box_size < header_size + 8:
                    raise UploadValidationError('Invalid video format box')
                brand = source.read(4)
                if brand in (b'heic', b'heix', b'avif', b'mif1', b'msf1'):
                    raise UploadValidationError('Image container declared as video')
                if suffix == '.mov' and brand != b'qt  ':
                    raise UploadValidationError('Video brand does not match MOV')
                if suffix == '.mp4' and brand == b'qt  ':
                    raise UploadValidationError('Video brand does not match MP4')
                saw_format = True
            saw_movie |= kind == b'moov'
            source.seek(offset + box_size)
    if not saw_movie or (suffix == '.mp4' and not saw_format):
        raise UploadValidationError('Missing video container structure')


def validate_file(path: Path) -> None:
    """Check a staged file's size and consistency with its approved suffix."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise UnsupportedUploadFormatError('Unsupported file format')
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise UploadTooLargeError('File exceeds 20 MiB limit')
    if size == 0:
        raise UploadValidationError('Empty file')
    try:
        if suffix in IMAGE_FORMATS:
            _validate_image(path, suffix)
        elif suffix in OFFICE_PARTS:
            _validate_office(path, suffix)
        elif suffix == '.pdf':
            with path.open('rb') as source:
                if source.read(5) != b'%PDF-':
                    raise UploadValidationError('Invalid PDF signature')
                source.seek(0)
                reader = PdfReader(source, strict=True)
                if reader.is_encrypted:
                    raise UploadValidationError('Encrypted PDF is unsupported')
        elif suffix == '.mp3':
            MP3(path)
        else:
            _validate_video(path, suffix)
    except (UnidentifiedImageError, Image.DecompressionBombError, BadZipFile,
            PdfReadError, HeaderNotFoundError, OSError, SyntaxError, ValueError,
            EOFError, RuntimeError) as error:
        if isinstance(error, UploadValidationError):
            raise
        raise UploadValidationError('Malformed file or content/format mismatch') from error


@contextmanager
def staged_upload(source: BinaryIO, filename: str) -> Iterator[Path]:
    """Copy from the current stream position, validate, yield, then delete.

    Caller owns and closes source. Process the yielded path inside the context.
    Never use the client filename as a filesystem path.
    """
    if not filename or '\x00' in filename:
        raise UploadValidationError('Invalid filename')
    suffix = Path(filename.replace('\\', '/')).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise UnsupportedUploadFormatError('Unsupported file format')
    with TemporaryDirectory(prefix='metadata-inspector-') as directory:
        path = Path(directory) / ('upload' + suffix)
        total = 0
        with path.open('xb') as output:
            path.chmod(0o600)
            while chunk := source.read(CHUNK_BYTES):
                total += len(chunk)
                if total > MAX_FILE_BYTES:
                    raise UploadTooLargeError('File exceeds 20 MiB limit')
                output.write(chunk)
        validate_file(path)
        yield path
