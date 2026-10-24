"""Host-owned exact-type classifications; unknown tools fail closed."""
CAPABILITIES = frozenset({'read_only', 'workspace_mutation', 'command_execution',
                          'external_side_effect', 'metadata_only'})


def validate_file_access(value, patch_mode):
    if type(value) is not str or value not in ('read_only', 'legacy_confirm'):
        raise ValueError('coding.file_access must be read_only or legacy_confirm')
    if value == 'legacy_confirm' and patch_mode != 'off':
        raise ValueError('legacy write and native Patch are mutually exclusive')


def native_capability(tool):
    from .file import ReadFileTool, WriteFileTool
    from .list_files import ListFilesTool
    from .search_code import SearchCodeTool
    from .read_file_range import ReadFileRangeTool
    from .git_tools import GitStatusTool, GitDiffTool
    from .patch import ApplyPatchTool
    from .run_command import RunCommandTool
    from .skill import SkillTool
    from ..agent.planning import PlanningTool
    from ..agent.task_contract import ContractTool
    from ..mcp_client.discovery import DiscoveryTool
    from ..mcp_client.adapter import MCPToolAdapter
    groups = {
        'read_only': (ReadFileTool, ListFilesTool, SearchCodeTool, ReadFileRangeTool,
                      GitStatusTool, GitDiffTool, SkillTool),
        'metadata_only': (PlanningTool, DiscoveryTool, ContractTool),
        'workspace_mutation': (WriteFileTool, ApplyPatchTool),
        'command_execution': (RunCommandTool,),
        'external_side_effect': (MCPToolAdapter,),
    }
    return next((cap for cap, types in groups.items() if type(tool) in types), None)
