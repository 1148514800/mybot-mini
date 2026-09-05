"""Sanitization entry points for checkpoint data."""

from .store import ActiveTaskCheckpointStore

sanitize_tool_arguments = ActiveTaskCheckpointStore._safe_tool_arguments
sanitize_browser_state = ActiveTaskCheckpointStore._sanitize_browser_state

__all__ = ["sanitize_tool_arguments", "sanitize_browser_state"]
