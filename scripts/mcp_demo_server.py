"""Trusted local demo: stdout is MCP protocol only. No network or file access."""
from mcp.server import MCPServer

server = MCPServer('mybot-demo',log_level='ERROR')


@server.tool()
def add(a: float,b: float) -> float:
    """Add two numbers."""
    return a+b


@server.tool()
def echo(message: str) -> str:
    """Return the supplied text."""
    return message


if __name__=='__main__':
    server.run(transport='stdio')
