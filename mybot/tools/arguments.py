"""Bound raw native JSON before decoding; reject duplicate keys and non-finite values."""
import json
import math


def parse_object(raw, *, max_bytes, size_error='arguments_too_large', max_depth=12):
    def invalid(*_): raise ValueError('invalid_arguments')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: invalid()
            result[key] = value
        return result
    if isinstance(raw, str):
        if len(raw) > max_bytes: raise ValueError(size_error)
        try:
            if len(raw.encode('utf-8')) > max_bytes: raise ValueError(size_error)
        except UnicodeEncodeError: raise ValueError('invalid_utf8') from None
        try: raw = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)
        except (ValueError, RecursionError): raise ValueError('invalid_arguments') from None
    if not isinstance(raw, dict): invalid()
    pending = [(raw, 0)]; nodes = 0; budget = max_bytes
    while pending:
        value, depth = pending.pop(); nodes += 1
        if depth > max_depth or nodes > 2048: invalid()
        if isinstance(value, (dict, list)):
            if len(value) > 128: raise ValueError(size_error)
            children = [v for pair in value.items() for v in pair] if isinstance(value, dict) else value
            pending.extend((v, depth + 1) for v in children)
        elif isinstance(value, str):
            if len(value) > budget: raise ValueError(size_error)
            try: budget -= len(value.encode('utf-8'))
            except UnicodeEncodeError: raise ValueError('invalid_utf8') from None
            if budget < 0: raise ValueError(size_error)
        elif type(value) not in (int, float, bool, type(None)) or (type(value) is float and not math.isfinite(value)):
            invalid()
    try: body = json.dumps(raw, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    except (ValueError, TypeError, UnicodeError): raise ValueError('invalid_arguments') from None
    if len(body) > max_bytes: raise ValueError(size_error)
    return json.loads(body)  # Caller receives an independent, bounded snapshot.
