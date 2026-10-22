"""Channel-local redaction and bounded display. Not an authorization mechanism."""
import re
from ..mcp_client.approval import CREDENTIAL


def redact(value, secrets=()):
    if isinstance(value, str):
        value = value[:32768]
        for secret in secrets:
            if isinstance(secret, str) and len(secret) >= 6: value = value.replace(secret, '[已隐藏]')
        value = CREDENTIAL.sub('[已隐藏]', value)
        value = re.sub(r'(?i)((?:api[_-]?key|password|passwd|secret|authorization|access[_-]?token)\s*[:=]\s*)[^\n,;]+', r'\1[已隐藏]', value)
        # Never publish an opaque receipt, even if a model copies it into prose/diff.
        value = re.sub(r'(?<![a-fA-F0-9])[a-fA-F0-9]{64}(?![a-fA-F0-9])', '[摘要已隐藏]', value)
        return value.encode('utf-8', errors='replace')[:32768].decode('utf-8', errors='ignore')
    if isinstance(value, dict): return {str(k)[:80]: redact(v, secrets) for k, v in list(value.items())[:64]}
    if isinstance(value, (list, tuple)): return [redact(v, secrets) for v in value[:64]]
    return value if type(value) in (bool, int, float) or value is None else None
