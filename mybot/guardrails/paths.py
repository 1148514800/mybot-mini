from __future__ import annotations

from enum import Enum
from pathlib import Path, PurePath


RUNTIME_MANAGED_DIRECTORIES = frozenset(
    {"memory", "sessions", "browser_profiles", "runs", "checkpoints", "artifacts"}
)
SENSITIVE_INSTRUCTION_NAMES = frozenset(
    {"agents.md", "soul.md", "user.md", "tools.md"}
)


class WorkspaceWriteKind(str, Enum):
    ORDINARY = "ordinary"
    RUNTIME_MANAGED = "runtime_managed"
    SENSITIVE = "sensitive"


def classify_workspace_write_path(
    path: str,
    workspace: Path | None = None,
) -> WorkspaceWriteKind:
    """Classify a write_file target using one shared workspace path policy."""
    raw = path.strip().replace("\\", "/")
    if not raw:
        return WorkspaceWriteKind.ORDINARY

    parts = _workspace_relative_parts(raw, workspace)
    if not parts:
        return WorkspaceWriteKind.ORDINARY

    lowered = tuple(part.lower() for part in parts)
    if lowered[0] in RUNTIME_MANAGED_DIRECTORIES:
        return WorkspaceWriteKind.RUNTIME_MANAGED
    if lowered[0] == "instructions":
        return WorkspaceWriteKind.SENSITIVE
    if lowered[-1] in SENSITIVE_INSTRUCTION_NAMES:
        return WorkspaceWriteKind.SENSITIVE
    if "config" in lowered[:-1]:
        return WorkspaceWriteKind.SENSITIVE
    return WorkspaceWriteKind.ORDINARY


def _workspace_relative_parts(
    path: str,
    workspace: Path | None,
) -> tuple[str, ...]:
    if workspace is not None:
        resolved_workspace = workspace.expanduser().resolve()
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = resolved_workspace / candidate
        try:
            relative = candidate.resolve().relative_to(resolved_workspace)
        except ValueError:
            pass
        else:
            parts = tuple(relative.parts)
            if parts and parts[0].lower() in {
                "workspace",
                resolved_workspace.name.lower(),
            }:
                return parts[1:]
            return parts

    parts = tuple(
        part
        for part in PurePath(path.lstrip("./")).parts
        if part not in {"", "."}
    )
    if parts and parts[0].lower() == "workspace":
        return parts[1:]
    if workspace is not None and parts:
        if parts[0].lower() == workspace.name.lower():
            return parts[1:]
    return parts
