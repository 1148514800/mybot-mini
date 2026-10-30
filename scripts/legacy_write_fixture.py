"""Historical test import name; v2 exposes read-only tools and no legacy writer."""
from mybot.tools import build_default_tool_registry


def legacy_registry(workspace, **kwargs):
    return build_default_tool_registry(workspace, **kwargs)
