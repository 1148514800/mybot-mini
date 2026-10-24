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
    private_arguments = True
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

    def __init__(self, workspace, *, enabled=False, approval_provider=None):
        super().__init__(workspace)
        self.enabled = enabled
        self.approval_provider = approval_provider

    async def execute(self, path: str, content: str, **kwargs) -> ToolResult:
        from .registry import ToolRegistry
        if not self.enabled or kwargs: return ToolRegistry.denied()
        from .patch import ApplyPatchTool
        from .file_approval import inspectable_write
        from .command_approval import authorize_command
        from .repository import RepositoryTool
        import hashlib
        patch = ApplyPatchTool(self.workspace, patch_mode='write', preview_receipt=True)
        patch.begin_receipt_scope()
        try:
            if type(path) is not str or type(content) is not str or len(content) > 32768:
                return ToolResult(False, error='legacy_write_uninspectable')
            raw = Path(path)
            if raw.is_absolute() or '..' in raw.parts or any((self.workspace / Path(*raw.parts[:i])).is_symlink() for i in range(1, len(raw.parts) + 1)):
                return ToolResult(False, error='legacy_unsafe_path')
            target = RepositoryTool.resolve(patch, path)
            relative = target.relative_to(self.workspace).as_posix()
            if target.exists():
                data = patch.read_bytes(target)
                old = data.decode('utf-8')
                if not old: return ToolResult(False, error='legacy_empty_overwrite_requires_native_patch')
                change = {'op': 'update', 'path': relative,
                          'expected_sha256': hashlib.sha256(data).hexdigest(),
                          'edits': [{'old_text': old, 'new_text': content}]}
            else:
                change = {'op': 'add', 'path': relative, 'content': content}
            preview = await patch.execute(changes=[change], dry_run=True)
            if not preview.success: return preview
            # Full intended bytes + version, never a truncated diff, are approved.
            request = inspectable_write(relative, content, change.get('expected_sha256'))
            approved, reason = await authorize_command(self.approval_provider, request)
            if not approved:
                return ToolResult(False, error=reason, metadata={'permission_denied': True, 'executed': False})
            result = await patch.execute(**preview.metadata['commit_arguments'])
            if result.success: result.output = f'wrote {len(content.encode("utf-8"))} bytes to {relative}'
            return result
        except (OSError, ValueError, UnicodeError):
            return ToolResult(False, error='legacy_write_preflight_failed')
        finally:
            patch.end_receipt_scope()
