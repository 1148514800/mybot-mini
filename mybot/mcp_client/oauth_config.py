"""Local trust declarations for a pre-registered public OAuth client."""
import re
from urllib.parse import urlsplit


def validate_oauth(auth):
    from .config import validate_http_url
    fields = {'type', 'issuer', 'client_id', 'scope', 'redirect_uri'}
    if set(auth) != fields:
        raise ValueError('Invalid OAuth configuration fields')
    validate_http_url(auth['issuer'])
    client = auth['client_id']
    if not isinstance(client, str) or not re.fullmatch(r'[A-Za-z0-9._~:/-]{1,256}', client):
        raise ValueError('OAuth client_id must be an explicit bounded identifier')
    scope = auth['scope']
    if (not isinstance(scope, str) or not 1 <= len(scope) <= 512
            or not re.fullmatch(r'[\x21\x23-\x5b\x5d-\x7e]+(?: [\x21\x23-\x5b\x5d-\x7e]+)*', scope)
            or len(scope.split()) != len(set(scope.split()))):
        raise ValueError('OAuth scope must explicitly list unique scope tokens')
    validate_http_url(auth['redirect_uri'])
    redirect = urlsplit(auth['redirect_uri'])
    if (redirect.scheme != 'http' or redirect.hostname != '127.0.0.1'
            or redirect.port is None or redirect.path != '/oauth/callback'):
        raise ValueError('OAuth redirect must be http://127.0.0.1:PORT/oauth/callback')
