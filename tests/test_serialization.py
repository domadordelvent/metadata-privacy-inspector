import json
from datetime import date, datetime, time, timezone
from decimal import Decimal
from fractions import Fraction
from enum import Enum

import pytest
from PIL.TiffImagePlugin import IFDRational
from serialization import to_json_value


def test_nested_extractor_types():
    original = {
        'date': datetime(2026, 10, 8, 12, 30, tzinfo=timezone.utc),
        'day': date(2026, 10, 8), 'time': time(12, 30),
        'bytes': b'\xff\x00', 'gps': (IFDRational(1, 2), Fraction(1, 4)),
        'decimal': Decimal('1.234567890123456789'),
        'nested': {123: [True, None, 'text', 7]},
    }
    result = to_json_value(original)
    assert result['date'] == '2026-10-08T12:30:00+00:00'
    assert result['day'] == '2026-10-08'
    assert result['time'] == '12:30:00'
    assert result['bytes'] == {'encoding': 'base64', 'data': '/wA='}
    assert result['gps'] == [0.5, 0.25]
    assert result['decimal'] == '1.234567890123456789'
    assert result['nested'] == {'123': [True, None, 'text', 7]}
    assert json.loads(json.dumps(result, allow_nan=False)) == result
    assert isinstance(original['gps'], tuple)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf'), Decimal('NaN'), IFDRational(0, 0)])
def test_nonfinite_values(value):
    assert to_json_value(value) is None


@pytest.mark.parametrize('value', [b'abc', bytearray(b'abc'), memoryview(b'abc')])
def test_binary_values(value):
    assert to_json_value(value) == {'encoding': 'base64', 'data': 'YWJj'}


def test_enum():
    class Field(Enum):
        TITLE = 'title'
    assert to_json_value(Field.TITLE) == 'title'


@pytest.mark.parametrize('value', [object(), {object(): 'value'}])
def test_unknown_types_rejected(value):
    with pytest.raises(TypeError):
        to_json_value(value)


def test_key_collision_rejected():
    with pytest.raises(ValueError):
        to_json_value({1: 'one', '1': 'other'})
