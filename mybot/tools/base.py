from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .result import ToolResult


class Tool(ABC):
    @property
    def requires_runtime_identity(self) -> bool:
        """Whether execution must receive identity from trusted runtime context."""
        return False

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
    async def execute(self, **kwargs) -> ToolResult | str: ...

    @property
    def runtime_metadata(self) -> dict[str, Any]:
        """Safe runtime provenance used by policy and tracing."""
        return {}

    def to_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
