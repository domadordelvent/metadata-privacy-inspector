from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess

from fastapi.testclient import TestClient
import pytest
from web_app import app


class Resources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
        self.ids = set()
        self.language = None
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'html':
            self.language = attrs.get('lang')
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        if tag == 'script':
            self.urls.append(attrs.get('src'))
        if tag == 'link':
            self.urls.append(attrs.get('href'))


def test_home_and_local_resources():
    with TestClient(app) as client:
        response = client.get('/')
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/html')
        assert response.headers['cache-control'] == 'no-store'
        assert "connect-src 'self'" in response.headers['content-security-policy']
        assert 'Metadata Privacy Inspector' in response.text
        assert 'Analyze File' in response.text
        assert '20 MiB' in response.text
        parser = Resources()
        parser.feed(response.text)
        assert parser.language == 'en'
        assert parser.urls == ['/static/style.css', '/static/app.js']
        assert {'file-input', 'upload-form', 'progress', 'metadata-body', 'findings-list', 'gps-panel', 'reset-button'} <= parser.ids
        for url in parser.urls:
            asset = client.get(url)
            assert asset.status_code == 200
            assert len(asset.content) > 100
        assert client.get('/static/style.css').headers['content-type'].startswith('text/css')
        assert 'javascript' in client.get('/static/app.js').headers['content-type']


def test_static_mount_does_not_expose_project():
    with TestClient(app) as client:
        assert client.get('/static/web_app.py').status_code == 404
        assert client.get('/static/%2e%2e/requirements.txt').status_code == 404


def test_frontend_interactions():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is required for the dependency-free JavaScript interaction tests')
    root = Path(__file__).resolve().parents[1]
    subprocess.run([node, '--check', 'static/app.js'], cwd=root, check=True, capture_output=True)
    subprocess.run([node, '--test', 'tests/frontend.test.cjs'], cwd=root, check=True, capture_output=True, text=True)
