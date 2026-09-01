from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolResult:
    """Structured internal result returned by a tool execution."""

    success: bool
    output: str = ""
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_legacy(cls, value: str) -> ToolResult:
        """Adapt an existing string-returning tool during the migration period."""
        if value.startswith("Error:"):
            return cls(success=False, error=value.removeprefix("Error:").strip())
        return cls(success=True, output=value)

    def to_text(self) -> str:
        """Serialize the result to compact text suitable for an LLM tool message."""
        parts: list[str] = []
        if not self.success:
            parts.append(f"Error: {self.error or 'Tool execution failed.'}")
        if self.output:
            parts.append(self.output)
        if self.metadata:
            metadata = json.dumps(
                self.metadata,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            parts.append(f"metadata={metadata}")
        return "\n\n".join(parts) or ("Success" if self.success else "Error: Tool execution failed.")


@dataclass(slots=True)
class BrowserResult(ToolResult):
    """Tool result enriched with browser action and session context."""

    action: str = ""
    session: str = ""
    url: str | None = None
    title: str | None = None

    def to_text(self) -> str:
        details = ["success" if self.success else "error"]
        if self.action:
            details.append(f"action={self.action}")
        if self.session:
            details.append(f"session={self.session}")
        if self.url:
            details.append(f"url={self.url}")
        if self.title:
            details.append(f"title={self.title}")

        parts = [f"[browser {' '.join(details)}]"]
        if self.error:
            parts.append(f"Error: {self.error}")
        if self.output:
            parts.append(self.output)
        if self.metadata:
            metadata = json.dumps(
                self.metadata,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            parts.append(f"metadata={metadata}")
        return "\n\n".join(parts)
