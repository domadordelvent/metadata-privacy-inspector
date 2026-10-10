"""Explicit, recursive conversion of extractor values to JSON primitives."""

import base64
from collections.abc import Mapping
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
import math
from numbers import Rational


def to_json_value(value):
    """Encode bytes as a tagged base64 object; reject unknown object types.

    Non-finite numbers become null. Unknown objects are never stringified,
    since their representations could expose internal paths or addresses.
    """
    if isinstance(value, Enum):
        return to_json_value(value.value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {'encoding': 'base64', 'data': base64.b64encode(value).decode('ascii')}
    if isinstance(value, Decimal):
        return str(value) if value.is_finite() else None
    if isinstance(value, (float, Rational)):
        number = float(value)
        return number if math.isfinite(number) else None
    # Pillow IFDRational is not registered as numbers.Rational.
    from PIL.TiffImagePlugin import IFDRational
    if isinstance(value, IFDRational):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if not isinstance(key, (str, int)):
                raise TypeError('Unsupported metadata key type')
            key = str(key)
            if key in result:
                raise ValueError('Duplicate serialized metadata key')
            result[key] = to_json_value(item)
        return result
    if isinstance(value, (list, tuple)):
        return [to_json_value(item) for item in value]
    raise TypeError('Unsupported metadata value type')
