from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class MCPServerStatus:
    name: str
    transport: str
    enabled: bool
    required: bool
    connected: bool = False
    error: str | None = None
    protocol_version: str | None = None
    tool_count: int = 0
    discovery_errors: list[str] = field(default_factory=list)


class MCPStartupError(RuntimeError):
    """Raised when a required MCP server cannot start."""

