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


notes: dict[str,str] = {}


def validate_note(key, content=None):
    if not isinstance(key,str) or not 1 <= len(key) <= 100:
        raise ValueError('key must contain 1-100 characters')
    if content is not None and (not isinstance(content,str) or len(content)>2000):
        raise ValueError('content must be a string with at most 2000 characters')


@server.tool()
def save_note(key: str,content: str) -> str:
    """Save a bounded note in process memory only."""
    validate_note(key,content)
    if key not in notes and len(notes)>=100:
        raise ValueError('note limit reached')
    notes[key] = content
    return 'saved'


@server.tool()
def read_note(key: str) -> str:
    """Read an existing in-memory note; fail when absent."""
    validate_note(key)
    if key not in notes:
        raise ValueError('note not found')
    return notes[key]


@server.tool()
def delete_note(key: str) -> str:
    """Delete an existing in-memory note."""
    validate_note(key)
    if key not in notes:
        raise ValueError('note not found')
    del notes[key]
    return 'deleted'


if __name__=='__main__':
    server.run(transport='stdio')
