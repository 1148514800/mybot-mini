"""Independent loopback Streamable HTTP demo; shares Phase 11 in-memory tools."""
import argparse

from mcp.server.transport_security import TransportSecuritySettings
from scripts.mcp_demo_server import server


def create_app(port=8765, *, json_response=True, stateless_http=False):
    security = TransportSecuritySettings(enable_dns_rebinding_protection=True,
        allowed_hosts=[f'127.0.0.1:{port}'],allowed_origins=[f'http://127.0.0.1:{port}'])
    return server.streamable_http_app(streamable_http_path='/mcp',host='127.0.0.1',
        json_response=json_response,stateless_http=stateless_http,transport_security=security)


def main():
    import uvicorn
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    if not 1<=args.port<=65535:parser.error('port must be 1-65535')
    uvicorn.run(create_app(args.port),host='127.0.0.1',port=args.port,log_level='error',access_log=False)


if __name__=='__main__':main()
