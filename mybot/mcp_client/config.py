import math
import ipaddress
from urllib.parse import urlsplit
import re
from copy import deepcopy

from .credentials import validate_auth


SERVER_NAME = re.compile(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z')
TOOL_NAME = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')


def validate_mcp(enabled, servers):
    if type(enabled) is not bool:
        raise ValueError('mcp.enabled must be a boolean')
    if not isinstance(servers,dict) or len(servers)>8:
        raise ValueError('mcp.servers must be an object with at most 8 servers')
    for name, server in servers.items():
        if not isinstance(name,str) or len(name)>20 or not SERVER_NAME.fullmatch(name):
            raise ValueError('MCP server names: 1-20 lowercase letters/digits with single hyphens; start with a letter')
        if not isinstance(server,dict):
            raise ValueError('Invalid MCP server configuration fields')
        transport = server.get('transport','stdio')
        if transport not in ('stdio','streamable_http'):
            raise ValueError('MCP transport must be stdio or streamable_http')
        fields = {'transport','allowed_tools','timeout_seconds','tool_policies'}
        fields |= {'command','args'} if transport == 'stdio' else {'url','auth'}
        if set(server)-fields:
            raise ValueError('Invalid MCP fields for selected transport')
        if transport == 'stdio':
            command = server.get('command')
            if not isinstance(command,str) or not command.strip() or '\x00' in command or len(command)>4096:
                raise ValueError('MCP command must be a nonempty executable path/name')
            args = server.get('args',[])
            if not isinstance(args,list) or len(args)>64 or any(not isinstance(a,str) or '\x00' in a or len(a)>8192 for a in args):
                raise ValueError('MCP args must be a list of bounded strings without NUL')
        else:
            validate_http_url(server.get('url'))
            validate_auth(server.get('auth', {'type':'none'}))
        allowed = server.get('allowed_tools')
        if not isinstance(allowed,list) or len(allowed)>64 or any(not isinstance(t,str) or not TOOL_NAME.fullmatch(t) for t in allowed) or len(set(allowed))!=len(allowed):
            raise ValueError('MCP allowed_tools must explicitly list unique valid tool names (maximum 64)')
        policies = server.get('tool_policies',{})
        if (not isinstance(policies,dict) or set(policies)-set(allowed)
                or any(not isinstance(v,str) or v not in ('allow','confirm','deny') for v in policies.values())):
            raise ValueError('MCP tool_policies must map allowed_tools names to allow, confirm or deny')
        timeout = server.get('timeout_seconds',10)
        if type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=120:
            raise ValueError('MCP timeout_seconds must be finite, greater than 0 and at most 120')
    return deepcopy(servers)


def validate_http_url(value):
    error = 'MCP URL must be credential-free HTTPS or literal loopback HTTP, without query/fragment'
    if (not isinstance(value,str) or not value or len(value)>2048 or not value.isascii()
            or any(ord(c)<=32 or ord(c)==127 for c in value) or any(c in value for c in ('?', '#', '\\'))):
        raise ValueError(error)
    try:
        url = urlsplit(value)
        host = url.hostname
        if url.scheme not in ('http','https') or not host or url.username is not None or url.password is not None:
            raise ValueError
        if url.port is not None and not 1<=url.port<=65535:
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
            if len(host)>253 or not all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?',label) for label in host.split('.')):
                raise ValueError
        if url.scheme == 'http' and (address is None or not address.is_loopback):
            raise ValueError
        if '%' in host:raise ValueError
    except ValueError:
        raise ValueError(error) from None
