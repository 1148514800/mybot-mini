import math
import re
from copy import deepcopy


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
        if not isinstance(server,dict) or set(server)-{'command','args','allowed_tools','timeout_seconds','tool_policies'}:
            raise ValueError('Invalid MCP server configuration fields')
        command = server.get('command')
        if not isinstance(command,str) or not command.strip() or '\x00' in command or len(command)>4096:
            raise ValueError('MCP command must be a nonempty executable path/name')
        args = server.get('args',[])
        if not isinstance(args,list) or len(args)>64 or any(not isinstance(a,str) or '\x00' in a or len(a)>8192 for a in args):
            raise ValueError('MCP args must be a list of bounded strings without NUL')
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
