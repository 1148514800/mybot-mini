"""Compatibility exports for checkpoint recovery adapters."""

from ..storage.checkpoints.serialization import (
    recent_task_from_checkpoint,
)

__all__ = [
    "recent_task_from_checkpoint",
]
