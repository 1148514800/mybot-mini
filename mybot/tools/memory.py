from __future__ import annotations

import json

from ..storage.memory import MemoryManager
from .base import Tool


class MemoryWriteTool(Tool):
    def __init__(self, memory_manager: MemoryManager):
        self.memory_manager = memory_manager

    @property
    def name(self) -> str:
        return "memory_write"

    @property
    def description(self) -> str:
        return "Write or update one long-term fact or preference."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Stable memory key"},
                "value": {"description": "Value to remember"},
            },
            "required": ["key", "value"],
        }

    async def execute(self, key: str, value, **kwargs) -> str:
        self.memory_manager.set(key, value)
        return json.dumps({"key": key.strip(), "value": value}, ensure_ascii=False)


class MemoryDeleteTool(Tool):
    def __init__(self, memory_manager: MemoryManager):
        self.memory_manager = memory_manager

    @property
    def name(self) -> str:
        return "memory_delete"

    @property
    def description(self) -> str:
        return "Delete one long-term memory when the user asks to forget it."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Memory key to delete"},
            },
            "required": ["key"],
        }

    async def execute(self, key: str, **kwargs) -> str:
        deleted = self.memory_manager.delete(key)
        return json.dumps({"key": key.strip(), "deleted": deleted}, ensure_ascii=False)
