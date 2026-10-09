from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


def _metadata_text(metadata: dict[str, Any]) -> str:
    return "metadata=" + json.dumps(
        metadata, ensure_ascii=False, separators=(",", ":")
    )


@dataclass(slots=True)
class ToolResult:
    """Result of one tool execution."""

    success: bool
    output: str = ""
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_text(self) -> str:
        parts: list[str] = []
        if not self.success:
            parts.append(f"Error: {self.error or 'tool execution failed'}")
        if self.output:
            parts.append(self.output)
        if self.metadata:
            parts.append(_metadata_text(self.metadata))
        return "\n\n".join(parts) or (
            "Success" if self.success else "Error: tool execution failed"
        )


class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]: ...

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult: ...

    def to_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
