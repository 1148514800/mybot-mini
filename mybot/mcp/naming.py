from __future__ import annotations

import hashlib
import re


MAX_TOOL_NAME_LENGTH = 64
_UNSAFE_CHARACTERS = re.compile(r"[^A-Za-z0-9_-]+")
_REPEATED_UNDERSCORES = re.compile(r"_{3,}")


def _hash_identity(server_name: str, tool_name: str, salt: str = "") -> str:
    value = f"{server_name}\0{tool_name}\0{salt}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()[:8]


def sanitize_name_component(value: str) -> str:
    sanitized = _UNSAFE_CHARACTERS.sub("_", value.strip())
    sanitized = _REPEATED_UNDERSCORES.sub("__", sanitized).strip("_-")
    return sanitized or "unnamed"


def build_mcp_tool_name(server_name: str, tool_name: str) -> str:
    server = sanitize_name_component(server_name)
    tool = sanitize_name_component(tool_name)
    candidate = f"mcp__{server}__{tool}"
    changed = (
        server != server_name
        or tool != tool_name
        or "__" in server_name
        or "__" in tool_name
        or len(candidate) > MAX_TOOL_NAME_LENGTH
    )
    if not changed:
        return candidate
    suffix = _hash_identity(server_name, tool_name)
    prefix = candidate[: MAX_TOOL_NAME_LENGTH - len(suffix) - 1].rstrip("_-")
    return f"{prefix}_{suffix}"


def resolve_name_collision(
    candidate: str,
    server_name: str,
    tool_name: str,
    occupied: set[str],
) -> str:
    if candidate not in occupied:
        return candidate
    for counter in range(1, 101):
        suffix = _hash_identity(server_name, tool_name, str(counter))
        prefix = candidate[: MAX_TOOL_NAME_LENGTH - len(suffix) - 1].rstrip(
            "_-"
        )
        resolved = f"{prefix}_{suffix}"
        if resolved not in occupied:
            return resolved
    raise ValueError(
        f"unable to resolve MCP tool name collision for {server_name}/{tool_name}"
    )
