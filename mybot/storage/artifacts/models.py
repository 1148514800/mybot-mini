from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class ArtifactRecord:
    artifact_id: str
    session_key: str
    task_id: str | None
    source_tool: str
    created_at: str
    original_chars: int
    stored_chars: int
    sha256: str
    redacted: bool
    storage_truncated: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ArtifactRecord":
        return cls(**{field: value[field] for field in cls.__dataclass_fields__})
