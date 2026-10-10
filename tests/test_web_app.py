from io import BytesIO
from pathlib import Path
import asyncio
import threading
import subprocess

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from docx import Document
from pypdf import PdfWriter
from starlette.requests import Request

import upload_handler
import web_app


@pytest.fixture
def client():
    with TestClient(web_app.app) as client:
        yield client


def png():
    output = BytesIO()
    Image.new('RGB', (10, 10)).save(output, format='PNG')
    return output.getvalue()


def test_inspects_image(client):
    response = client.post('/api/inspect', files={'file': ('picture.png', png(), 'text/plain')})
    assert response.status_code == 200
    result = response.json()
    assert set(result) == {'file', 'metadata', 'findings'}
    assert result['file'] == {'name': 'picture.png', 'extension': '.png', 'size_bytes': len(png()), 'mime_type': 'image/png'}
    assert result['metadata']['width'] == 10
    assert result['findings'] == []
    assert response.headers['cache-control'] == 'no-store'


def test_pdf_privacy_findings(client):
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.add_metadata({'/Author': 'Test Author'})
    writer.write(output)
    response = client.post('/api/inspect', files={'file': ('../../private.pdf', output.getvalue())})
    assert response.status_code == 200
    assert response.json()['file']['name'] == 'private.pdf'
    assert response.json()['metadata']['Author'] == 'Test Author'
    assert any(f['field'] == 'Author' for f in response.json()['findings'])
    assert 'metadata-inspector-' not in response.text


def test_docx_dates(client):
    output = BytesIO()
    Document().save(output)
    response = client.post('/api/inspect', files={'file': ('sample.docx', output.getvalue())})
    assert response.status_code == 200
    assert isinstance(response.json()['metadata']['CreationDate'], str)


@pytest.mark.parametrize('files, status', [
    ({'file': ('sample.txt', b'text')}, 415),
    ({'file': ('sample.png', b'bad')}, 422),
    ({'file': ('sample.jpg', png())}, 422),
    ({'file': ('sample.png', b'')}, 400),
    ({'other': ('sample.png', png())}, 400),
    ([('file', ('one.png', png())), ('file', ('two.png', png()))], 400),
])
def test_upload_errors(client, files, status):
    response = client.post('/api/inspect', files=files)
    assert response.status_code == status
    assert response.headers['cache-control'] == 'no-store'


def test_nonmultipart_and_missing_boundary(client):
    assert client.post('/api/inspect', json={}).status_code == 415
    response = client.post('/api/inspect', content=b'bad', headers={'content-type': 'multipart/form-data'})
    assert response.status_code == 400


def test_additional_fields_rejected(client):
    response = client.post('/api/inspect', files={'file': ('sample.png', png())}, data={'extra': 'field'})
    assert response.status_code == 400


@pytest.mark.parametrize('error', [RuntimeError('/internal/secret'), FileNotFoundError('/secret/ffprobe'), subprocess.TimeoutExpired('secret', 15)])
def test_internal_errors_are_private(client, monkeypatch, error):
    def inspect(path):
        raise error
    monkeypatch.setattr(web_app, 'inspect_file', inspect)
    response = client.post('/api/inspect', files={'file': ('sample.png', png())})
    assert response.status_code == 500
    assert response.json() == {'detail': 'Unable to analyse file'}
    assert response.headers['cache-control'] == 'no-store'


def test_extraction_error_is_422(client, monkeypatch):
    def inspect(path):
        raise ValueError('/internal/path')
    monkeypatch.setattr(web_app, 'inspect_file', inspect)
    response = client.post('/api/inspect', files={'file': ('sample.png', png())})
    assert response.status_code == 422
    assert '/internal' not in response.text


@pytest.mark.parametrize('fail', [False, True])
def test_temporary_cleanup(client, monkeypatch, tmp_path, fail):
    original = upload_handler.TemporaryDirectory
    monkeypatch.setattr(upload_handler, 'TemporaryDirectory', lambda **kw: original(dir=tmp_path, **kw))
    if fail:
        monkeypatch.setattr(web_app, 'inspect_file', lambda path: (_ for _ in ()).throw(RuntimeError('failed')))
    response = client.post('/api/inspect', files={'file': ('sample.png', png())})
    assert response.status_code == (500 if fail else 200)
    assert list(tmp_path.iterdir()) == []


def test_file_limit_is_independent_of_http_limit(client, monkeypatch):
    monkeypatch.setattr(upload_handler, 'MAX_FILE_BYTES', len(png()) - 1)
    response = client.post('/api/inspect', files={'file': ('sample.png', png())})
    assert response.status_code == 413


def test_declared_http_limit_prevents_multipart(client, monkeypatch):
    def forbidden(*a, **kw):
        pytest.fail('Multipart parser must not run')
    monkeypatch.setattr(Request, 'form', forbidden)
    response = client.post('/api/inspect', content=b'x', headers={
        'content-type': 'multipart/form-data; boundary=test',
        'content-length': str(web_app.MAX_REQUEST_BYTES + 1),
    })
    assert response.status_code == 413


@pytest.mark.parametrize('declared', [None, '1'])
def test_stream_limit_before_multipart(client, monkeypatch, declared):
    monkeypatch.setattr(web_app, 'MAX_REQUEST_BYTES', 10)
    monkeypatch.setattr(Request, 'form', lambda *a, **kw: pytest.fail('Parser ran'))
    headers = {'content-type': 'multipart/form-data; boundary=test'}
    if declared is not None:
        headers['content-length'] = declared
    response = client.post('/api/inspect', content=iter([b'x' * 6, b'y' * 5]), headers=headers)
    assert response.status_code == 413


@pytest.mark.parametrize('length', ['bad', '-1', '2'])
def test_invalid_or_false_length(client, length):
    response = client.post('/api/inspect', content=b'x', headers={
        'content-type': 'multipart/form-data; boundary=test', 'content-length': length,
    })
    assert response.status_code == 400


def test_body_limit_exact_boundary(client, monkeypatch):
    request = httpx.Request('POST', 'http://test/api/inspect', files={'file': ('sample.png', png())})
    body = request.read()
    monkeypatch.setattr(web_app, 'MAX_REQUEST_BYTES', len(body))
    assert client.post('/api/inspect', content=body, headers=request.headers).status_code == 200
    monkeypatch.setattr(web_app, 'MAX_REQUEST_BYTES', len(body) - 1)
    assert client.post('/api/inspect', content=body, headers=request.headers).status_code == 413


def test_chunked_valid_body(client):
    request = httpx.Request('POST', 'http://test/api/inspect', files={'file': ('sample.png', png())})
    body = request.read()
    response = client.post('/api/inspect', content=iter([body[:50], body[50:]]),
                           headers={'content-type': request.headers['content-type']})
    assert response.status_code == 200


def test_worker_does_not_block_event_loop(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    original = web_app.inspect_file
    def inspect(path):
        started.set()
        assert release.wait(timeout=5)
        return original(path)
    monkeypatch.setattr(web_app, 'inspect_file', inspect)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web_app.app), base_url='http://test') as client:
            task = asyncio.create_task(client.post('/api/inspect', files={'file': ('sample.png', png())}))
            try:
                async with asyncio.timeout(3):
                    while not started.is_set():
                        await asyncio.sleep(0.01)
                    response = await client.get('/missing')
                    assert response.status_code == 404
            finally:
                release.set()
            assert (await task).status_code == 200
    asyncio.run(run())


def test_truncated_multipart_rejected(client):
    request = httpx.Request('POST', 'http://test/api/inspect', files={'file': ('sample.png', png())})
    body = request.read()
    truncated = body[:body.rfind(b'--') - 10]
    response = client.post('/api/inspect', content=truncated, headers={'content-type': request.headers['content-type']})
    assert response.status_code == 400


@pytest.mark.parametrize('fail', [False, True])
def test_raw_body_and_upload_closed(client, monkeypatch, fail):
    from starlette.datastructures import UploadFile
    bodies = []
    closed_uploads = []
    original_body = web_app.SpooledTemporaryFile
    original_close = UploadFile.close
    def make_body(**kwargs):
        body = original_body(**kwargs)
        bodies.append(body)
        return body
    async def close(upload):
        await original_close(upload)
        closed_uploads.append(upload.file.closed)
    monkeypatch.setattr(web_app, 'SpooledTemporaryFile', make_body)
    monkeypatch.setattr(UploadFile, 'close', close)
    if fail:
        monkeypatch.setattr(web_app, 'inspect_file', lambda path: (_ for _ in ()).throw(RuntimeError('failed')))
    response = client.post('/api/inspect', files={'file': ('sample.png', png())})
    assert response.status_code == (500 if fail else 200)
    assert bodies and all(body.closed for body in bodies)
    assert closed_uploads == [True]


def test_serialization_failure_is_private(client, monkeypatch):
    monkeypatch.setattr(web_app, 'inspect_file', lambda path: {
        'file': {}, 'metadata': {'unknown': object()}, 'findings': [],
    })
    response = client.post('/api/inspect', files={'file': ('sample.png', png())})
    assert response.status_code == 500
    assert response.json() == {'detail': 'Unable to analyse file'}


def test_binary_metadata_and_gps(client, monkeypatch):
    from PIL.TiffImagePlugin import IFDRational
    monkeypatch.setattr(web_app, 'inspect_file', lambda path: {
        'file': {}, 'metadata': {'raw': b'\xff', 'GPS': {'latitude': IFDRational(1, 2)}},
        'findings': [{'field': 'GPS', 'value': (0.5, 1.25), 'description': 'Location'}],
    })
    response = client.post('/api/inspect', files={'file': ('sample.png', png())})
    assert response.status_code == 200
    assert response.json()['metadata']['raw'] == {'encoding': 'base64', 'data': '/w=='}
    assert response.json()['findings'][0]['value'] == [0.5, 1.25]
