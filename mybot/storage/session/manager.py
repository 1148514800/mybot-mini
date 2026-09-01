from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Session:
    key: str
    messages: list[dict] = field(default_factory=list)

    def get_history(self, max_messages: int = 50) -> list[dict]:
        recent = self.messages[-max_messages:]
        for index, message in enumerate(recent):
            if message.get("role") == "user":
                return recent[index:]
        return recent

    def build_prompt_history(self, max_recent_messages: int = 12) -> list[dict]:
        return self.get_history(max_messages=max_recent_messages)


class SessionManager:
    def __init__(self, workspace: Path):
        self.dir = workspace / "sessions"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Session] = {}

    def _path_for(self, key: str) -> Path:
        filename = key.replace(":", "_").replace("/", "_").replace("\\", "_")
        return self.dir / f"{filename}.jsonl"

    def get_or_create(self, key: str) -> Session:
        if key in self._cache:
            return self._cache[key]
        session = self._load(key) or Session(key=key)
        self._cache[key] = session
        return session

    def save(self, session: Session) -> None:
        path = self._path_for(session.key)
        with open(path, "w", encoding="utf-8") as handle:
            for message in session.messages:
                handle.write(json.dumps(message, ensure_ascii=False) + "\n")

    def _load(self, key: str) -> Session | None:
        path = self._path_for(key)
        if not path.exists():
            return None

        messages: list[dict] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            return Session(key=key)

        for line in lines:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                # Keep a single damaged record from making the whole session unusable.
                continue
            if not isinstance(item, dict):
                continue
            if item.get("type") == "meta":
                continue
            messages.append(item)

        return Session(key=key, messages=messages)
