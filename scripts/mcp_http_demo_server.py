"""Independent loopback Streamable HTTP demo; shares Phase 11 in-memory tools."""
import argparse
import hmac

from mybot.mcp_client.credentials import load_credential
from mybot.mcp_client.errors import HTTPTransportError

from mcp.server.transport_security import TransportSecuritySettings
from scripts.mcp_demo_server import server


def create_app(port=8765, *, json_response=True, stateless_http=False, require_token_env=None):
    security = TransportSecuritySettings(enable_dns_rebinding_protection=True,
        allowed_hosts=[f'127.0.0.1:{port}'],allowed_origins=[f'http://127.0.0.1:{port}'])
    credential = (load_credential({'type':'bearer_env','token_env':require_token_env})
                  if require_token_env is not None else None)
    app = server.streamable_http_app(streamable_http_path='/mcp',host='127.0.0.1',
        json_response=json_response,stateless_http=stateless_http,transport_security=security)

    if credential is None:
        return app
    expected = {}
    credential.apply(expected)
    expected = expected['Authorization'].encode('ascii')

    async def authenticated(scope, receive, send):
        if scope['type'] == 'http':
            values = [v for k,v in scope.get('headers', []) if k.lower() == b'authorization']
            if len(values) != 1 or not hmac.compare_digest(values[0], expected):
                await send({'type':'http.response.start','status':401,
                            'headers':[(b'www-authenticate',b'Bearer')]})
                await send({'type':'http.response.body','body':b'Unauthorized'})
                return
        await app(scope, receive, send)
    return authenticated


def main():
    import uvicorn
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--require-token-env')
    args=parser.parse_args()
    if not 1<=args.port<=65535:parser.error('port must be 1-65535')
    try:
        app = create_app(args.port,require_token_env=args.require_token_env)
    except (ValueError,HTTPTransportError):
        parser.error('invalid or missing demo credential configuration')
    uvicorn.run(app,host='127.0.0.1',port=args.port,log_level='error',access_log=False)


if __name__=='__main__':main()
