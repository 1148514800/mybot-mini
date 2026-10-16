"""Explicit environment references and a connection-time credential snapshot."""
import os
import re
from dataclasses import dataclass, field

from .errors import HTTPTransportError

ENV_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,127}\Z')
BEARER_TOKEN = re.compile(r'[A-Za-z0-9._~+/-]+=*\Z')
MAX_TOKEN_BYTES = 4096


def validate_auth(auth):
    if not isinstance(auth, dict):
        raise ValueError('Invalid MCP auth configuration')
    kind = auth.get('type')
    if kind == 'oauth_pkce':
        from .oauth_config import validate_oauth
        validate_oauth(auth)
        return
    if kind == 'none' and set(auth) == {'type'}:
        return
    if (kind == 'bearer_env' and set(auth) == {'type', 'token_env'}
            and isinstance(auth['token_env'], str) and ENV_NAME.fullmatch(auth['token_env'])):
        return
    raise ValueError('MCP auth requires none, bearer_env or oauth_pkce with explicit local references')


@dataclass(frozen=True)
class Credential:
    _token: str = field(repr=False)

    def apply(self, headers):
        headers['Authorization'] = 'Bearer ' + self._token


def load_credential(auth):
    validate_auth(auth)
    if auth['type'] == 'none':
        return None
    if auth['type'] != 'bearer_env':
        raise HTTPTransportError('credential_provider_mismatch')
    token = os.environ.get(auth['token_env'])
    if token is None:
        raise HTTPTransportError('credential_missing')
    # RFC 6750 b64token, bounded ASCII only; no whitespace or header controls.
    if not token or len(token) > MAX_TOKEN_BYTES or not BEARER_TOKEN.fullmatch(token):
        raise HTTPTransportError('credential_invalid')
    return Credential(token)
