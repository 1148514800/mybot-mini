from __future__ import annotations

from pathlib import Path

from .base import Tool


class WorkspaceFileTool(Tool):
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()

    def _resolve_path(self, path: str) -> Path:
        target = Path(path).expanduser()
        if not target.is_absolute():
            target = self.workspace / target

        target = target.resolve()
        if not self._is_within_workspace(target):
            raise ValueError(f"Path outside workspace: {path}")
        return target

    def _is_within_workspace(self, target: Path) -> bool:
        try:
            target.relative_to(self.workspace)
        except ValueError:
            return False
        return True


class ReadFileTool(WorkspaceFileTool):
    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read file contents."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
            },
            "required": ["path"],
        }

    async def execute(self, path: str, **kwargs) -> str:
        try:
            target = self._resolve_path(path)
            if not target.exists():
                return f"Error: Not found: {path}"
            return target.read_text(encoding="utf-8")[:50000]
        except Exception as exc:
            return f"Error: {exc}"


class WriteFileTool(WorkspaceFileTool):
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Write content to a file."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "content": {"type": "string", "description": "Content"},
            },
            "required": ["path", "content"],
        }

    async def execute(self, path: str, content: str, **kwargs) -> str:
        try:
            target = self._resolve_path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"Wrote {len(content)} bytes to {target}"
        except Exception as exc:
            return f"Error: {exc}"
