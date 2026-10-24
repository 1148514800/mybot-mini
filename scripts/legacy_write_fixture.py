"""Explicit offline compatibility setup; uses the real per-call production guard."""
from mybot.mcp_client.approval import ApprovalDecision
from mybot.tools import build_default_tool_registry


async def approve_legacy(request):
    return ApprovalDecision.APPROVE


def legacy_registry(workspace, **kwargs):
    return build_default_tool_registry(workspace, file_access='legacy_confirm',
                                       file_approval_provider=approve_legacy, **kwargs)
