from __future__ import annotations

from pathlib import Path

from .base import Tool, ToolResult


class FileTool(Tool):
    """Shared workspace path handling for read_file and write_file."""

    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()

    def _resolve(self, path: str) -> Path:
        target = Path(path).expanduser()
        if not target.is_absolute():
            target = self.workspace / target
        target = target.resolve()
        if not target.is_relative_to(self.workspace):
            raise ValueError(f"path outside workspace: {path}")
        return target


class ReadFileTool(FileTool):
    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read a file from the workspace."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File path"}},
            "required": ["path"],
        }

    async def execute(self, path: str, **kwargs) -> ToolResult:
        try:
            target = self._resolve(path)
            if not target.is_file():
                return ToolResult(success=False, error=f"not found: {path}")
            with target.open(encoding="utf-8") as stream:
                text = stream.read(50001)
            truncated = len(text)>50000
            marker = "\n[文件内容已裁剪，不能据此声称完整读取或分析]"
            return ToolResult(success=True, output=text[:50000]+(marker if truncated else ""),
                              metadata={'truncated':True} if truncated else {})
        except Exception as exc:
            return ToolResult(success=False, error=f"{type(exc).__name__}: {exc}")


class WriteFileTool(FileTool):
    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Write content to a file in the workspace."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "content": {"type": "string", "description": "File content"},
            },
            "required": ["path", "content"],
        }

    async def execute(self, path: str, content: str, **kwargs) -> ToolResult:
        try:
            target = self._resolve(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            size = len(content.encode("utf-8"))
            return ToolResult(success=True, output=f"wrote {size} bytes to {path}")
        except Exception as exc:
            return ToolResult(success=False, error=f"{type(exc).__name__}: {exc}")
