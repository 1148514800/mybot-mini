from __future__ import annotations

from pathlib import Path

from .base import Tool, ToolResult
from .file import ReadFileTool, WriteFileTool
from .list_files import ListFilesTool


class ToolRegistry:
    """Name-indexed tools with schema lookup and one execution boundary."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def get_parameters(self, name: str) -> dict:
        tool = self._tools.get(name)
        return dict(tool.parameters) if tool else {}

    def get_tool(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def iter_tools(self) -> tuple[Tool, ...]:
        return tuple(self._tools.values())

    def is_metadata(self, name: str) -> bool:
        tool = self.get_tool(name)
        return tool is not None and not getattr(tool, 'provides_execution_evidence', True)

    def get_definitions(self, visible_names=None) -> list[dict]:
        visible = None if visible_names is None else frozenset(visible_names)
        return [tool.to_schema() for tool in self._tools.values()
                if visible is None or tool.name in visible]

    async def execute(self, name: str, params: dict) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(success=False, error=f"unknown tool '{name}'")
        try:
            result = await tool.execute(**dict(params))
        except Exception as exc:
            return ToolResult(success=False, error=f"{type(exc).__name__}: {exc}")
        if isinstance(result, ToolResult):
            return result
        return ToolResult(success=False, error=f"tool returned {type(result).__name__}")


def build_default_tool_registry(workspace: Path) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in (
        ReadFileTool(workspace),
        WriteFileTool(workspace),
        ListFilesTool(workspace),
    ):
        registry.register(tool)
    return registry
