"""Local-only REST API; run with python web_app.py."""

import base64
from pathlib import Path
import subprocess
from tempfile import SpooledTemporaryFile
from zipfile import BadZipFile

import anyio
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header
from pypdf.errors import PdfReadError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.requests import ClientDisconnect

from metadata_cleaner import CleaningRejected, clean_file
from inspection import inspect_file
from serialization import to_json_value
from upload_handler import (
    CHUNK_BYTES, MAX_FILE_BYTES, UnsupportedUploadFormatError,
    UploadTooLargeError, UploadValidationError, staged_upload,
)

# Allow multipart framing without increasing the actual file limit.
MAX_REQUEST_BYTES = MAX_FILE_BYTES + 64 * 1024
NO_STORE = {'Cache-Control': 'no-store'}
app = FastAPI(debug=False)
STATIC_DIRECTORY = Path(__file__).resolve().parent / 'static'
app.mount('/static', StaticFiles(directory=STATIC_DIRECTORY), name='static')


@app.get('/', include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIRECTORY / 'index.html', headers={
        **NO_STORE,
        'Content-Security-Policy': (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        ),
        'X-Content-Type-Options': 'nosniff',
        'Referrer-Policy': 'no-referrer',
    })


def error_response(status: int, detail: str) -> JSONResponse:
    return JSONResponse({'detail': detail}, status_code=status, headers=NO_STORE)


def _inspect_upload(upload: UploadFile):
    with staged_upload(upload.file, upload.filename) as path:
        try:
            result = inspect_file(path)
        except (PdfReadError, BadZipFile, ValueError, KeyError, EOFError,
                subprocess.CalledProcessError) as error:
            raise UploadValidationError('File could not be analysed') from error
        # Display only the basename supplied by the client, never the staging path.
        result['file']['name'] = Path(upload.filename.replace('\\', '/')).name
        return JSONResponse(to_json_value(result), headers=NO_STORE)


@app.post('/api/inspect', openapi_extra={
    'requestBody': {
        'required': True,
        'content': {'multipart/form-data': {'schema': {
            'type': 'object', 'required': ['file'],
            'properties': {'file': {'type': 'string', 'format': 'binary'}},
        }}},
    },
})
async def inspect_upload(request: Request):
    return await _receive_upload(request, _inspect_upload)


@app.post('/api/clean')
async def clean_upload(request: Request):
    return await _receive_upload(request, _clean_upload)


def _clean_upload(upload: UploadFile):
    with staged_upload(upload.file, upload.filename) as source:
        output = source.with_name('clean' + source.suffix)
        report = clean_file(source, output)
        # All disk temporaries disappear before the response is sent. The bounded
        # response owns the bytes, so interrupted downloads cannot leak files.
        data = base64.b64encode(output.read_bytes()).decode('ascii')
        return JSONResponse({
            'name': 'clean' + source.suffix, 'data': data, 'report': report,
        }, headers=NO_STORE)


async def _receive_upload(request: Request, processor):
    """Receive exactly one bounded multipart field named file."""
    body = SpooledTemporaryFile(max_size=1024 * 1024, mode='w+b')
    try:
        lengths = request.headers.getlist('content-length')
        if lengths:
            if (len(lengths) != 1 or len(lengths[0]) > 20
                    or not lengths[0].isascii() or not lengths[0].isdigit()):
                return error_response(400, 'Invalid request length')
            if int(lengths[0]) > MAX_REQUEST_BYTES:
                return error_response(413, 'Request exceeds size limit')
        if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'multipart/form-data':
            return error_response(415, 'Expected multipart/form-data')
        _, parameters = parse_options_header(request.headers['content-type'])
        boundary = parameters.get(b'boundary')
        if not boundary or len(boundary) > 200 or b'\r' in boundary or b'\n' in boundary:
            return error_response(400, 'Invalid multipart boundary')

        # Fully bound the raw body BEFORE invoking any multipart parser.
        # Do not rely on Content-Length: chunked and false declarations are counted.
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > MAX_REQUEST_BYTES:
                return error_response(413, 'Request exceeds size limit')
            await run_in_threadpool(body.write, chunk)
        if lengths and total != int(lengths[0]):
            return error_response(400, 'Request length mismatch')
        # Some multipart parsers return completed fields despite a missing final
        # delimiter. Require an explicit terminator; epilogues are not accepted.
        terminator = b'--' + boundary + b'--'
        tail_size = len(terminator) + 4
        await run_in_threadpool(body.seek, max(0, total - tail_size))
        tail = await run_in_threadpool(body.read, tail_size)
        if not tail.rstrip(b'\r\n').endswith(terminator):
            return error_response(400, 'Incomplete multipart upload')
        await run_in_threadpool(body.seek, 0)

        async def receive():
            chunk = await run_in_threadpool(body.read, CHUNK_BYTES)
            return {'type': 'http.request', 'body': chunk, 'more_body': bool(chunk)}

        bounded_request = Request(request.scope, receive)
        async with bounded_request.form(max_files=1, max_fields=0, max_part_size=1024) as form:
            items = form.multi_items()
            if len(items) != 1 or items[0][0] != 'file' or not isinstance(items[0][1], UploadFile):
                return error_response(400, 'Expected one file field')
            upload = items[0][1]
            if not upload.filename or '\x00' in upload.filename:
                return error_response(400, 'Invalid filename')
            if upload.size == 0:
                return error_response(400, 'Empty file')
            await upload.seek(0)
            # Keep the form and staged resources alive until the worker finishes.
            with anyio.CancelScope(shield=True):
                return await run_in_threadpool(processor, upload)
    except CleaningRejected as error:
        return error_response(422, str(error))
    except UploadTooLargeError:
        return error_response(413, 'File exceeds 20 MiB limit')
    except UnsupportedUploadFormatError:
        return error_response(415, 'Unsupported file format')
    except UploadValidationError:
        return error_response(422, 'Invalid file or content does not match its format')
    except (HTTPException, MultipartParseError, ClientDisconnect):
        return error_response(400, 'Malformed or incomplete upload')
    except Exception:
        return error_response(500, 'Unable to analyse file')
    finally:
        with anyio.CancelScope(shield=True):
            await run_in_threadpool(body.close)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8000)
