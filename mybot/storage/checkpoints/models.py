"""Checkpoint schema constants and recovered active row representation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CHECKPOINT_SCHEMA_VERSION = 1
DEFAULT_RECENT_TASK_TTL_SECONDS = 86_400


@dataclass(slots=True)
class RecoveredActiveCheckpoint:
    kind: str
    task_state: dict[str, Any]
    payload: dict[str, Any]
