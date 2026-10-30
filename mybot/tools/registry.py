from __future__ import annotations

from pathlib import Path

from .base import Tool, ToolResult
from .file import ReadFileTool
from .list_files import ListFilesTool


class ToolRegistry:
    """Name-indexed tools with schema lookup and one execution boundary."""

    def __init__(self, *, mutation_enabled=False) -> None:
        if type(mutation_enabled) is not bool: raise ValueError('mutation_enabled must be boolean')
        self._tools: dict[str, Tool] = {}
        self._capabilities: dict[str, str] = {}
        self.mutation_enabled = mutation_enabled
        self.execution_observer = None

    def register(self, tool: Tool, *, capability=None) -> None:
        # Only host code supplies capability. Tool parameters/results cannot grant it.
        from .authority import native_capability, CAPABILITIES
        capability = native_capability(tool) if capability is None else capability
        if capability is not None and capability not in CAPABILITIES:
            raise ValueError('invalid tool capability')
        self._tools[tool.name] = tool
        self._capabilities[tool.name] = capability

    def permitted(self, name: str) -> bool:
        if name == 'write_file': return False
        capability = self._capabilities.get(name)
        if capability is None: return False
        if capability == 'workspace_mutation' and not self.mutation_enabled: return False
        # Native tool modes and remote MCP policies remain additional independent gates.
        from ..mcp_client.adapter import MCPToolAdapter
        tool = self._tools.get(name)
        if type(tool) is MCPToolAdapter:
            server = tool.manager.servers.get(tool.server, {})
            return (tool.remote_name in server.get('allowed_tools', []) and
                    server.get('tool_policies', {}).get(tool.remote_name, 'confirm') != 'deny')
        return True

    @staticmethod
    def denied() -> ToolResult:
        return ToolResult(False, error='tool_authority_denied', metadata={
            'permission_denied': True, 'executed': False, 'execution_evidence': False,
            'authority_denied': True})

    @staticmethod
    def retired() -> ToolResult:
        return ToolResult(False, error='TOOL_RETIRED_WRITE_FILE', metadata={
            'permission_denied': True, 'executed': False, 'execution_evidence': False,
            'authority_denied': True})

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
                if self.permitted(tool.name) and (visible is None or tool.name in visible)]

    async def execute(self, name: str, params: dict) -> ToolResult:
        if name == 'write_file': return self.retired()
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(success=False, error=f"unknown tool '{name}'")
        if not self.permitted(name): return self.denied()
        observer = self.execution_observer
        token = observer.begin(name, params, tool, self._capabilities[name]) if observer is not None else None
        try:
            result = await tool.execute(**dict(params))
        except Exception as exc:
            result = ToolResult(success=False, error=f"{type(exc).__name__}: {exc}")
        if not isinstance(result, ToolResult):
            result = ToolResult(success=False, error=f"tool returned {type(result).__name__}")
        if observer is not None: observer.complete(token, result)
        return result


def build_default_tool_registry(workspace: Path, *, coding_enabled=False, patch_mode='off', preview_receipt=False, command=None, command_approval_provider=None) -> ToolRegistry:
    if type(coding_enabled) is not bool:raise ValueError('coding_enabled must be a boolean')
    if type(patch_mode) is not str or patch_mode not in ('off','preview','write'):
        raise ValueError('invalid patch_mode')
    if patch_mode != 'off' and not coding_enabled:raise ValueError('patch_mode requires coding_enabled')
    if type(preview_receipt) is not bool or (preview_receipt and patch_mode == 'off'):
        raise ValueError('invalid_receipt_mode')
    from .command_config import validate_command
    command = {} if command is None else command
    settings = validate_command(command, coding_enabled=coding_enabled, patch_mode=patch_mode)
    registry = ToolRegistry(mutation_enabled=patch_mode != 'off')
    for tool in (
        ReadFileTool(workspace),
        ListFilesTool(workspace),
    ):
        registry.register(tool)
    if coding_enabled:
        from .search_code import SearchCodeTool
        from .repo_map import RepoMapTool
        from .read_file_range import ReadFileRangeTool
        from .git_tools import GitStatusTool,GitDiffTool
        registry.register(SearchCodeTool(workspace))
        registry.register(RepoMapTool(workspace))
        registry.register(ReadFileRangeTool(workspace, include_version=patch_mode != 'off'))
        for cls in (GitStatusTool,GitDiffTool):registry.register(cls(workspace))
        if patch_mode != 'off':
            from .patch import ApplyPatchTool
            registry.register(ApplyPatchTool(workspace, patch_mode=patch_mode, preview_receipt=preview_receipt))
    if settings.mode != 'off':
        from .run_command import RunCommandTool
        registry.register(RunCommandTool(workspace, command=command, patch_mode=patch_mode, approval_provider=command_approval_provider))
    return registry


def build_configured_tool_registry(config, *, command_approval_provider):
    """Map shared config fields; approvals and resource ownership belong to the host."""
    return build_default_tool_registry(config.workspace, coding_enabled=config.coding_enabled,
        patch_mode=config.coding_patch_mode, preview_receipt=config.coding_preview_receipt,
        command=config.coding_command, command_approval_provider=command_approval_provider)
