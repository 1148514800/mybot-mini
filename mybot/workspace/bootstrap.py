from __future__ import annotations

from pathlib import Path


DEFAULT_INSTRUCTION_FILES = {
    "SOUL.md": "# Soul\n\n我是 Mini Agent，一个有帮助的 AI 助手。\n\n友善、简洁、准确。\n",
    "AGENTS.md": "# Agent Instructions\n\n- 先说意图，再调工具\n- 修改文件前先读取\n- 不确定时主动询问\n",
    "USER.md": "# User Profile\n\n（请编辑此文件来告诉 Bot 你的信息）\n",
    "TOOLS.md": "# Tools\n\n（可在此补充工具使用约定）\n",
}


def init_instructions(instructions_dir: Path) -> None:
    instructions_dir.mkdir(parents=True, exist_ok=True)

    for name, content in DEFAULT_INSTRUCTION_FILES.items():
        path = instructions_dir / name
        if not path.exists():
            path.write_text(content, encoding="utf-8")


def init_workspace(workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "memory").mkdir(exist_ok=True)
    (workspace / "sessions").mkdir(exist_ok=True)
