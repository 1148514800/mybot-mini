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


def build_default_tool_registry(workspace: Path, *, coding_enabled=False, patch_mode='off', command=None, command_approval_provider=None) -> ToolRegistry:
    if type(coding_enabled) is not bool:raise ValueError('coding_enabled must be a boolean')
    if type(patch_mode) is not str or patch_mode not in ('off','preview','write'):
        raise ValueError('invalid patch_mode')
    if patch_mode != 'off' and not coding_enabled:raise ValueError('patch_mode requires coding_enabled')
    from .command_config import validate_command
    command = {} if command is None else command
    settings = validate_command(command, coding_enabled=coding_enabled, patch_mode=patch_mode)
    registry = ToolRegistry()
    for tool in (
        ReadFileTool(workspace),
        *([WriteFileTool(workspace)] if patch_mode == 'off' else []),
        ListFilesTool(workspace),
    ):
        registry.register(tool)
    if coding_enabled:
        from .search_code import SearchCodeTool
        from .read_file_range import ReadFileRangeTool
        from .git_tools import GitStatusTool,GitDiffTool
        registry.register(SearchCodeTool(workspace))
        registry.register(ReadFileRangeTool(workspace, include_version=patch_mode != 'off'))
        for cls in (GitStatusTool,GitDiffTool):registry.register(cls(workspace))
        if patch_mode != 'off':
            from .patch import ApplyPatchTool
            registry.register(ApplyPatchTool(workspace, patch_mode=patch_mode))
    if settings.mode != 'off':
        from .run_command import RunCommandTool
        registry.register(RunCommandTool(workspace, command=command, patch_mode=patch_mode, approval_provider=command_approval_provider))
    return registry
