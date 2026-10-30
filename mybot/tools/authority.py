"""Host-owned exact-type classifications; unknown tools fail closed."""
CAPABILITIES = frozenset({'read_only', 'workspace_mutation', 'command_execution',
                          'external_side_effect', 'metadata_only'})


def native_capability(tool):
    from .file import ReadFileTool
    from .list_files import ListFilesTool
    from .repo_map import RepoMapTool
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
        'read_only': (RepoMapTool, ReadFileTool, ListFilesTool, SearchCodeTool, ReadFileRangeTool,
                      GitStatusTool, GitDiffTool, SkillTool),
        'metadata_only': (PlanningTool, DiscoveryTool, ContractTool),
        'workspace_mutation': (ApplyPatchTool,),
        'command_execution': (RunCommandTool,),
        'external_side_effect': (MCPToolAdapter,),
    }
    return next((cap for cap, types in groups.items() if type(tool) in types), None)
