from __future__ import annotations

import json
from pathlib import Path


class MemoryManager:
    def __init__(self, workspace: Path):
        self.dir = workspace / "memory"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "memory.json"

    def _normalize(self, data: object) -> dict[str, object]:
        if not isinstance(data, dict):
            return {}

        # Read the previous categorized format without keeping it in the runtime model.
        if any(
            key in data
            for key in ("user_preferences", "project_facts", "custom_facts")
        ):
            memories: dict[str, object] = {}
            for section_name in ("user_preferences", "project_facts"):
                section = data.get(section_name)
                if isinstance(section, dict):
                    memories.update(self._clean_mapping(section))

            custom_facts = data.get("custom_facts")
            if isinstance(custom_facts, list):
                for item in custom_facts:
                    if not isinstance(item, dict):
                        continue
                    key = str(item.get("key", "")).strip()
                    if key:
                        memories[key] = item.get("value")
            return memories

        return self._clean_mapping(data)

    def _clean_mapping(self, data: dict) -> dict[str, object]:
        memories: dict[str, object] = {}
        for raw_key, value in data.items():
            key = str(raw_key).strip()
            if key:
                memories[key] = value
        return memories

    def load(self) -> dict[str, object]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Cannot read memory file: {self.path}") from exc
        return self._normalize(data)

    def save(self, memories: dict[str, object]) -> None:
        normalized = self._clean_mapping(memories)
        temporary_path = self.path.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(self.path)

    def get_memory_summary(self) -> str:
        try:
            memories = self.load()
        except ValueError:
            return ""
        if not memories:
            return ""

        lines = ["# Memory"]
        for key, value in memories.items():
            if value in (None, ""):
                continue
            if isinstance(value, (dict, list)):
                rendered = json.dumps(value, ensure_ascii=False)
            else:
                rendered = str(value)
            lines.append(f"- {key}: {rendered}")
        return "" if len(lines) == 1 else "\n".join(lines)

    def set(self, key: str, value: object) -> None:
        lookup = key.strip()
        if not lookup:
            raise ValueError("key is required")
        memories = self.load()
        memories[lookup] = value
        self.save(memories)

    def delete(self, key: str) -> bool:
        lookup = key.strip()
        if not lookup:
            return False
        memories = self.load()
        if lookup not in memories:
            return False
        del memories[lookup]
        self.save(memories)
        return True
