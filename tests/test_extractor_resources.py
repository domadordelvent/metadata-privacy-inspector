import subprocess
from types import SimpleNamespace

import pytest
import metadata_extractor


@pytest.mark.parametrize('fail', [False, True])
def test_xlsx_closed_even_when_property_access_fails(monkeypatch, fail):
    class Workbook:
        closed = False
        @property
        def properties(self):
            if fail:
                raise RuntimeError('properties failed')
            return SimpleNamespace(title='Title', subject=None, creator=None,
                keywords=None, description=None, lastModifiedBy=None,
                created=None, modified=None, category=None)
        def close(self):
            self.closed = True
    workbook = Workbook()
    monkeypatch.setattr(metadata_extractor, 'load_workbook', lambda *a, **kw: workbook)
    if fail:
        with pytest.raises(RuntimeError):
            metadata_extractor.extract_xlsx_metadata('sample.xlsx')
    else:
        assert metadata_extractor.extract_xlsx_metadata('sample.xlsx') == {'Title': 'Title'}
    assert workbook.closed


def test_ffprobe_timeout(monkeypatch):
    def run(args, **kwargs):
        assert kwargs['timeout'] == 15
        assert kwargs['check'] is True
        assert isinstance(args, list)
        raise subprocess.TimeoutExpired(args, kwargs['timeout'])
    monkeypatch.setattr(metadata_extractor.subprocess, 'run', run)
    with pytest.raises(subprocess.TimeoutExpired):
        metadata_extractor.extract_video_metadata('sample.mp4')
