from __future__ import annotations

from .base import Tool
from .result import ToolResult


class RequestUserInputTool(Tool):
    """Runtime control tool used by AgentLoop to pause for clarification."""

    @property
    def name(self) -> str:
        return "request_user_input"

    @property
    def description(self) -> str:
        return (
            "Ask one necessary clarification question and pause this task. "
            "Use for missing information, login completion, or ambiguous "
            "choices. The next user message resumes the same task and browser "
            "session. Do not use this for risky tool approval."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The concise question shown to the user",
                }
            },
            "required": ["question"],
        }

    @property
    def runtime_metadata(self) -> dict:
        return {"runtime_control": "clarification"}

    async def execute(self, question: str, **kwargs) -> ToolResult:
        normalized = question.strip()
        if not normalized:
            return ToolResult(
                success=False,
                error="Clarification question must not be empty.",
            )
        return ToolResult(
            success=True,
            output=normalized,
            metadata={"runtime_control": "clarification"},
        )
