from __future__ import annotations

from pathlib import Path
from typing import Any


SYSTEM_RULES = (
    "你是一个运行在本地工作区中的 AI 助手。优先基于文件内容和工具结果回答，不要凭空猜测。"
    "你可以使用提供的工具操作工作区文件。修改文件前先读取；不确定时向用户询问。"
    "普通问候、问答或单步工具任务直接执行，不创建计划。多步骤操作可通过 create_plan 创建2到6步计划。"
    "计划只属于当前用户任务，不复用历史计划状态。每步先 update_plan 为 in_progress，"
    "再执行实际工具，根据工具结果 update_plan 为 completed 或 failed，按顺序推进。"
    "没有实际成功工具结果的步骤不能标为 completed；失败必须报告，不能跳过或宣称全部成功。"
)


class ContextBuilder:
    bootstrap_files = ("AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md")

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.instructions_dir = workspace / "instructions"

    def build_messages(self, user_message: str,
                       history: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        instructions = [f"# Mini Agent\n\n{SYSTEM_RULES}\n\n工作区：{self.workspace}"]
        for filename in self.bootstrap_files:
            path = self.instructions_dir / filename
            if path.exists():
                instructions.append(f"## {filename}\n\n{path.read_text(encoding='utf-8')}")
        return [
            {"role": "system", "content": "\n\n---\n\n".join(instructions)},
            *(history or []),
            {"role": "user", "content": user_message},
        ]
