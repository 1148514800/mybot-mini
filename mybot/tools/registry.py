from __future__ import annotations

from pathlib import Path

from ..storage.memory import MemoryManager
from .base import Tool
from .browser import (
    BrowserAttachTool,
    BrowserClickTool,
    BrowserCloseTool,
    BrowserEvalTool,
    BrowserInspectTool,
    BrowserGotoTool,
    BrowserLinksTool,
    BrowserOpenTool,
    BrowserPressTool,
    BrowserSnapshotTool,
    BrowserTypeTool,
    BrowserVerifyTool,
    BrowserTabTool,
    BrowserSessionManager,
)
from .exec import ExecTool
from .file_tools import ReadFileTool, WriteFileTool
from .memory import MemoryDeleteTool, MemoryWriteTool
from .result import ToolResult
from .runtime import RequestUserInputTool


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def get_runtime_metadata(self, name: str) -> dict:
        tool = self._tools.get(name)
        return dict(tool.runtime_metadata) if tool else {}

    def get_definitions(self) -> list[dict]:
        return [tool.to_schema() for tool in self._tools.values()]

    async def execute(self, name: str, params: dict) -> ToolResult:
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(success=False, error=f"Unknown tool '{name}'")
        try:
            result = await tool.execute(**params)
            if isinstance(result, ToolResult):
                return result
            if isinstance(result, str):
                return ToolResult.from_legacy(result)
            return ToolResult(
                success=False,
                error=(
                    f"Tool '{name}' returned unsupported result type "
                    f"{type(result).__name__}"
                ),
            )
        except Exception as exc:
            return ToolResult(success=False, error=f"{type(exc).__name__}: {exc}")


def build_default_tool_registry(
    workspace: Path,
    memory_manager: MemoryManager | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    browser_sessions = BrowserSessionManager()
    registry.register(ExecTool(workspace))
    registry.register(RequestUserInputTool())
    registry.register(BrowserAttachTool(browser_sessions))
    registry.register(BrowserOpenTool(workspace, browser_sessions))
    registry.register(BrowserSnapshotTool(browser_sessions))
    registry.register(BrowserGotoTool(browser_sessions))
    registry.register(BrowserTabTool(browser_sessions))
    registry.register(BrowserClickTool(browser_sessions))
    registry.register(BrowserTypeTool(browser_sessions))
    registry.register(BrowserPressTool(browser_sessions))
    registry.register(BrowserLinksTool(browser_sessions))
    registry.register(BrowserInspectTool(browser_sessions))
    registry.register(BrowserVerifyTool(browser_sessions))
    registry.register(BrowserEvalTool(browser_sessions))
    registry.register(BrowserCloseTool(browser_sessions))
    if memory_manager:
        registry.register(MemoryWriteTool(memory_manager))
        registry.register(MemoryDeleteTool(memory_manager))
    registry.register(ReadFileTool(workspace))
    registry.register(WriteFileTool(workspace))
    return registry
