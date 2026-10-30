from __future__ import annotations

from .base import Tool, ToolResult
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..skills.registry import SkillRegistry


class SkillTool(Tool):
    provides_execution_evidence = False

    def __init__(self, registry: SkillRegistry, name: str):
        self.registry = registry
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return ("Read a complete trusted local SKILL.md; this does not execute instructions."
                if self.name == "load_skill" else
                "Read an optional UTF-8 text reference under a skill's references/ directory.")

    @property
    def parameters(self) -> dict:
        properties = {"name": {"type": "string"}}
        if self.name == "read_skill_reference":
            properties["path"] = {"type": "string", "description": "Skill-relative references/... text path"}
        return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}

    async def execute(self, name: str, **kwargs) -> ToolResult:
        if self.name == "load_skill" and kwargs:
            return ToolResult(success=False, error="load_skill accepts only name")
        if self.name == "read_skill_reference" and set(kwargs) != {"path"}:
            return ToolResult(success=False, error="read_skill_reference requires name and path")
        if self.name == "read_skill_reference" and (not isinstance(kwargs["path"], str) or not kwargs["path"].startswith("references/")):
            return ToolResult(success=False, error="Reference path must start with references/")
        try:
            return ToolResult(success=True, output=self.registry.read(name, **kwargs))
        except (OSError, ValueError) as exc:
            return ToolResult(success=False, error=str(exc))
