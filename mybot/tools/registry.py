from __future__ import annotations

from pathlib import Path

from .base import Tool, ToolResult
from .browser import (
    BrowserAttachTool,
    BrowserClickTool,
    BrowserCloseTool,
    BrowserEvalTool,
    BrowserGotoTool,
    BrowserInspectTool,
    BrowserLinksTool,
    BrowserOpenTool,
    BrowserPressTool,
    BrowserSnapshotTool,
    BrowserTabTool,
    BrowserTypeTool,
    BrowserVerifyTool,
)
from .exec import ExecTool
from .file import ReadFileTool, WriteFileTool


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

    def get_definitions(self) -> list[dict]:
        return [tool.to_schema() for tool in self._tools.values()]

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
        ExecTool(workspace),
        ReadFileTool(workspace),
        WriteFileTool(workspace),
        BrowserAttachTool(),
        BrowserOpenTool(workspace),
        BrowserGotoTool(),
        BrowserTabTool(),
        BrowserCloseTool(),
        BrowserSnapshotTool(),
        BrowserClickTool(),
        BrowserTypeTool(),
        BrowserPressTool(),
        BrowserLinksTool(),
        BrowserInspectTool(),
        BrowserVerifyTool(),
        BrowserEvalTool(),
    ):
        registry.register(tool)
    return registry
