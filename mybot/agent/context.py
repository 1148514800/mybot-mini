from __future__ import annotations

from pathlib import Path


SYSTEM_RULES = (
    "你是一个运行在本地工作区中的 AI 助手。优先基于文件内容和工具结果回答，不要凭空猜测。"
    "你可以使用 read_file 和 write_file 操作工作区文件。修改文件前先读取；不确定时向用户询问。"
)


class ContextBuilder:
    bootstrap_files = ("AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md")

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.instructions_dir = workspace / "instructions"

    def build_messages(self, user_message: str) -> list[dict[str, str]]:
        instructions = [f"# Mini Agent\n\n{SYSTEM_RULES}\n\n工作区：{self.workspace}"]
        for filename in self.bootstrap_files:
            path = self.instructions_dir / filename
            if path.exists():
                instructions.append(f"## {filename}\n\n{path.read_text(encoding='utf-8')}")
        return [
            {"role": "system", "content": "\n\n---\n\n".join(instructions)},
            {"role": "user", "content": user_message},
        ]
