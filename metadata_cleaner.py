"""Conservative metadata removal. Never writes to the input file."""

import hashlib
from pathlib import Path
import shutil
import struct
import zlib
from zipfile import ZipFile

from lxml import etree
from PIL import Image
from mutagen.id3 import delete as delete_id3
from mutagen.mp3 import MP3
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, ArrayObject, IndirectObject, StreamObject

from inspection import inspect_file
from serialization import to_json_value
from upload_handler import validate_file

SUPPORTED_CLEANING = {'.jpg', '.jpeg', '.png', '.pdf', '.docx', '.xlsx', '.pptx', '.mp3'}


class CleaningRejected(ValueError):
    """A fixed user-facing explanation; never interpolate parser errors."""


def reject(message='This file structure cannot be cleaned safely.'):
    raise CleaningRejected(message)


def _orientation(path):
    with Image.open(path) as image:
        exif = image.getexif()
        if exif.get(274, 1) != 1:
            reject('This image needs its orientation metadata. Cleaning is unavailable to preserve its appearance.')
        nested = exif.get_ifd(34665) if 34665 in exif else {}
        colour = {**dict(exif), **nested}
        if colour.get(40961, 1) != 1 or any(tag in colour for tag in (301, 318, 319, 42240)):
            reject('This image uses EXIF colour information that cannot be removed without risking its appearance.')


def _jpeg(data):
    if data[:2] != b'\xff\xd8':
        reject()
    output = bytearray(data[:2])
    pos = 2
    removed = 0
    while pos < len(data):
        start = pos
        if data[pos] != 255:
            reject()
        while pos < len(data) and data[pos] == 255:
            pos += 1
        if pos >= len(data):
            reject()
        marker = data[pos]
        pos += 1
        if marker == 0xD9:
            output.extend(data[start:pos])
            if pos != len(data):
                reject('This image contains trailing data that cannot be cleaned safely.')
            return bytes(output), removed
        if marker in (0, 0xD8) or 0xD0 <= marker <= 0xD7:
            reject()
        if pos + 2 > len(data):
            reject()
        length = int.from_bytes(data[pos:pos+2], 'big')
        end = pos + length
        if length < 2 or end > len(data):
            reject()
        payload = data[pos+2:end]
        strip = marker in (0xE1, 0xED, 0xFE)
        if 0xE0 <= marker <= 0xEF:
            known = ((marker == 0xE0 and payload.startswith(b'JFIF\0')) or
                     (marker == 0xE2 and payload.startswith(b'ICC_PROFILE\0')) or
                     (marker == 0xEE and payload.startswith(b'Adobe')) or
                     (marker == 0xE1 and payload.startswith((b'Exif\0\0', b'http://ns.adobe.com/'))) or
                     marker == 0xED)
            if not known:
                reject('This JPEG contains unsupported auxiliary data or provenance information.')
        if strip:
            removed += 1
        else:
            output.extend(data[start:end])
        pos = end
        if marker == 0xDA:
            # Copy entropy-coded data verbatim through stuffed/restart markers.
            scan_start = pos
            while pos < len(data):
                if data[pos] != 255:
                    pos += 1
                    continue
                following = pos + 1
                while following < len(data) and data[following] == 255:
                    following += 1
                if following >= len(data):
                    reject()
                if data[following] == 0 or 0xD0 <= data[following] <= 0xD7:
                    pos = following + 1
                    continue
                break
            output.extend(data[scan_start:pos])
    reject()


def _png(data):
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        reject()
    output = bytearray(data[:8])
    pos = 8
    removed = 0
    allowed = {b'IHDR', b'PLTE', b'IDAT', b'IEND', b'tRNS', b'cHRM', b'gAMA',
               b'iCCP', b'sRGB', b'sBIT', b'bKGD', b'pHYs'}
    removable = {b'eXIf', b'tEXt', b'zTXt', b'iTXt', b'tIME'}
    while pos + 12 <= len(data):
        length, kind = struct.unpack('>I4s', data[pos:pos+8])
        end = pos + 12 + length
        if end > len(data):
            reject()
        payload = data[pos+8:end-4]
        if zlib.crc32(kind + payload) & 0xffffffff != int.from_bytes(data[end-4:end], 'big'):
            reject()
        if kind in removable:
            removed += 1
        elif kind in allowed:
            output.extend(data[pos:end])
        else:
            reject('This PNG contains animation, provenance or unsupported auxiliary data. Cleaning is unavailable.')
        pos = end
        if kind == b'IEND':
            if length or pos != len(data):
                reject()
            return bytes(output), removed
    reject()


def _verify_pixels(source, output):
    with Image.open(source) as before, Image.open(output) as after:
        if (before.size, before.mode) != (after.size, after.mode):
            reject('The image preservation check failed. No cleaned copy is available.')
        if before.tobytes() != after.tobytes():
            reject('The image preservation check failed. No cleaned copy is available.')
        if before.info.get('icc_profile') != after.info.get('icc_profile'):
            reject('The image colour profile could not be preserved.')


def _office(source, output):
    core_type = 'http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties'
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    with ZipFile(source) as archive:
        core_parts = []
        for entry in archive.infolist():
            if '_xmlsignatures' in entry.filename.lower() or 'vbaproject' in entry.filename.lower():
                reject('Signed or macro-enabled documents cannot be cleaned safely.')
            if entry.filename.endswith('.rels') or entry.filename in ('[Content_Types].xml', 'docProps/app.xml'):
                raw = archive.read(entry)
                root = etree.fromstring(raw, parser)
                if root.getroottree().docinfo.doctype:
                    reject()
                for node in root.iter():
                    kind = node.get('Type', '') + node.get('ContentType', '')
                    if etree.QName(node).localname == 'DigitalSignature':
                        reject('This document contains digital signature information. Cleaning is unavailable.')
                    if 'digital-signature' in kind.lower():
                        reject('This document contains a digital signature. Cleaning would invalidate it.')
                    if node.get('Type') == core_type:
                        if entry.filename != '_rels/.rels' or node.get('TargetMode') == 'External':
                            reject()
                        core_parts.append(node.get('Target', '').lstrip('/'))
        if len(core_parts) != 1 or core_parts[0] != 'docProps/core.xml':
            reject('This document has an unsupported properties structure.')
        core = etree.fromstring(archive.read(core_parts[0]), parser)
        if core.getroottree().docinfo.doctype or core.tag != '{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}coreProperties':
            reject()
        for child in list(core):
            core.remove(child)
        core.attrib.clear()
        core.text = None
        replacement = etree.tostring(core, xml_declaration=True, encoding='UTF-8')
        with ZipFile(output, 'w') as cleaned:
            for entry in archive.infolist():
                cleaned.writestr(entry, replacement if entry.filename == core_parts[0] else archive.read(entry))
    with ZipFile(source) as before, ZipFile(output) as after:
        if before.namelist() != after.namelist():
            reject()
        for name in before.namelist():
            if name != 'docProps/core.xml' and before.read(name) != after.read(name):
                reject('The document preservation check failed.')
    return ['Office core properties'], ['Only core properties were removed. Custom properties, comments, revisions, notes and embedded files may still contain personal information.']


def _pdf_fingerprint(value, depth=0, budget=None):
    if budget is None:
        budget = [10000]
    budget[0] -= 1
    if budget[0] < 0 or depth > 60:
        reject('This PDF is too complex to verify safely.')
    if isinstance(value, IndirectObject):
        return _pdf_fingerprint(value.get_object(), depth+1, budget)
    if isinstance(value, DictionaryObject):
        if value.get('/Type') == '/Sig' or value.get('/FT') == '/Sig' or '/ByteRange' in value:
            reject('This PDF contains a digital signature. Cleaning would invalidate it.')
        forbidden = {'/AcroForm', '/Perms', '/Annots', '/AA', '/A', '/OpenAction', '/EmbeddedFiles', '/XFA', '/RichMedia', '/Metadata', '/PieceInfo'}
        if forbidden.intersection(value.keys()):
            reject('This PDF contains forms, annotations or unsupported embedded structures. Cleaning is unavailable.')
        pairs = tuple((str(key), _pdf_fingerprint(item, depth+1, budget))
                      for key, item in sorted(value.items())
                      if key != '/Parent' and not (isinstance(value, StreamObject) and key in ('/Length', '/Filter', '/DecodeParms')))
        if isinstance(value, StreamObject):
            filters = value.get('/Filter')
            if isinstance(filters, ArrayObject):
                filters = filters[0] if len(filters) == 1 else 'unsupported'
            if filters not in (None, '/FlateDecode', '/DCTDecode'):
                reject('This PDF uses compressed content that cannot be verified safely.')
            if filters == '/FlateDecode':
                decoder = zlib.decompressobj()
                decoded = decoder.decompress(value._data, 20 * 1024 * 1024 + 1)
                if len(decoded) > 20 * 1024 * 1024 or decoder.unconsumed_tail or not decoder.eof:
                    reject('This PDF exceeds the safe decompression limit.')
            content = value.get_data()
            if len(content) > 20 * 1024 * 1024:
                reject('This PDF exceeds the safe decompression limit.')
            return (pairs, hashlib.sha256(content).hexdigest())
        return pairs
    if isinstance(value, ArrayObject):
        return tuple(_pdf_fingerprint(item, depth+1, budget) for item in value)
    if isinstance(value, bytes):
        return bytes(value)
    return (type(value).__name__, str(value))


def _pdf(source, output):
    with source.open('rb') as stream:
        reader = PdfReader(stream, strict=True)
        if reader.is_encrypted:
            reject('Encrypted PDFs cannot be cleaned safely.')
        root = reader.trailer['/Root']
        if '/Perms' in root or '/AcroForm' in root:
            reject('Signed PDFs or PDFs with forms cannot be cleaned safely.')
        if set(root) - {'/Type', '/Pages', '/Metadata'}:
            reject('This PDF has additional document features that cannot be preserved with sufficient confidence.')
        fingerprint = _pdf_fingerprint(root['/Pages'])
        writer = PdfWriter(clone_from=reader)
        writer.metadata = None
        writer.root_object.pop('/Metadata', None)
        writer.compress_identical_objects(remove_duplicates=False, remove_unreferenced=True)
        with output.open('wb') as destination:
            writer.write(destination)
    with output.open('rb') as stream:
        cleaned = PdfReader(stream, strict=True)
        if cleaned.metadata or cleaned.xmp_metadata or _pdf_fingerprint(cleaned.trailer['/Root']['/Pages']) != fingerprint:
            reject('The PDF preservation check failed. No cleaned copy is available.')
    return ['PDF document information and document XMP'], ['Only document-level metadata was removed. Page contents may still identify people; complex or signed PDFs are not supported.']


def _mp3_payload(data):
    start = 0
    if data.startswith(b'ID3'):
        if len(data) < 10 or data[3] not in (2, 3, 4) or data[5] & 0x10 or any(b & 128 for b in data[6:10]):
            reject('This MP3 has an unsupported ID3 structure.')
        size = 0
        for byte in data[6:10]:
            size = (size << 7) | byte
        start = 10 + size
        if start > len(data):
            reject()
    end = len(data) - 128 if len(data) >= 128 and data[-128:-125] == b'TAG' else len(data)
    if b'APETAGEX' in data[max(start, end-1024):]:
        reject('This MP3 contains additional tags that cannot be cleaned safely.')
    return data[start:end]


def _mp3(source, output):
    audio = MP3(source)
    if audio.tags and any(key.startswith('SIGN') for key in audio.tags):
        reject('This MP3 contains signature information. Cleaning is unavailable.')
    payload = _mp3_payload(source.read_bytes())
    shutil.copyfile(source, output)
    delete_id3(output, delete_v1=True, delete_v2=True)
    if output.read_bytes() != payload:
        reject('The audio preservation check failed. No cleaned copy is available.')
    return ['ID3v1 and ID3v2 tags'], ['ID3 titles, artwork and other ID3 features are removed. Audio bytes are preserved. Duration estimates may change after tag removal; technical playback information and other embedded information may remain.']


def clean_file(source: Path, output: Path) -> dict:
    """Clean into a new destination, validate and reanalyse; delete failures."""
    source, output = Path(source), Path(output)
    if source.resolve() == output.resolve() or output.exists():
        reject('Cleaning requires a separate, new output file.')
    suffix = source.suffix.lower()
    if suffix not in SUPPORTED_CLEANING:
        reject('Metadata removal is not supported for this format. MP4 and MOV cleaning is disabled.')
    if output.suffix.lower() != suffix:
        reject()
    validate_file(source)
    original_hash = hashlib.sha256(source.read_bytes()).digest()
    before = inspect_file(source)
    owned_output = False
    try:
        with output.open('xb'):
            pass
        owned_output = True
        output.chmod(0o600)
        if suffix in {'.jpg', '.jpeg', '.png'}:
            _orientation(source)
            data, count = (_png if suffix == '.png' else _jpeg)(source.read_bytes())
            output.write_bytes(data)
            _verify_pixels(source, output)
            operations = [f'{count} removable image metadata blocks']
            warnings = ['Image pixels and colour profiles were preserved. Technical and colour metadata may remain; visible image content is unchanged.']
        elif suffix in {'.docx', '.xlsx', '.pptx'}:
            operations, warnings = _office(source, output)
        elif suffix == '.pdf':
            operations, warnings = _pdf(source, output)
        else:
            operations, warnings = _mp3(source, output)
        validate_file(output)
        after = inspect_file(output)
        if hashlib.sha256(source.read_bytes()).digest() != original_hash:
            reject('The original integrity check failed.')
        # openpyxl manufactures creator/current dates for missing XML elements.
        # Correct only the verification report using the actual package fields;
        # do not present reader defaults as stored metadata.
        if suffix == '.xlsx':
            field_tags = {'Author': 'creator', 'CreationDate': 'created', 'ModDate': 'modified'}
            for path, result in ((source, before), (output, after)):
                with ZipFile(path) as archive:
                    core = etree.fromstring(archive.read('docProps/core.xml'), etree.XMLParser(resolve_entities=False, no_network=True))
                    present = {etree.QName(child).localname for child in core if isinstance(child.tag, str) and child.text}
                for field, tag in field_tags.items():
                    if tag not in present:
                        result['metadata'].pop(field, None)
                result['findings'] = [finding for finding in result['findings'] if finding['field'] in result['metadata']]
            warnings.append('The XLSX reader supplies default author/dates for absent properties. These are not stored in the cleaned copy and are excluded from this verification report.')
        old, new = to_json_value(before['metadata']), to_json_value(after['metadata'])
        return {
            'removed_fields': [key for key in old if key not in new],
            'changed_fields': [key for key in old if key in new and old[key] != new[key]],
            'remaining_metadata': new,
            'remaining_findings': to_json_value(after['findings']),
            'operations': operations, 'warnings': warnings,
            'notice': 'This is a selectively cleaned copy, not a guarantee that all metadata or personal information has been removed.',
        }
    except BaseException:
        if owned_output:
            output.unlink(missing_ok=True)
        raise
