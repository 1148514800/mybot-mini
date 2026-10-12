from .base import ToolResult
from .file import FileTool


class ListFilesTool(FileTool):
    @property
    def name(self):
        return "list_files"

    @property
    def description(self):
        return "List files and directories in a workspace directory."

    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path; use '.' for workspace root"}
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    async def execute(self, path: str, **kwargs) -> ToolResult:
        try:
            target = self._resolve(path)
            if not target.is_dir():
                return ToolResult(success=False, error=f"not a directory: {path}")
            entries = sorted(target.iterdir(), key=lambda p: p.name.lower())
            lines = [f"{'[DIR]' if p.is_dir() else '[FILE]'} {p.name}" for p in entries[:100]]
            return ToolResult(success=True, output="\n".join(lines) or "(empty directory)",
                              metadata={"total": len(entries), "shown": len(lines)})
        except Exception as exc:
            return ToolResult(success=False, error=f"{type(exc).__name__}: {exc}")
