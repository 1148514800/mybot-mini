from __future__ import annotations

from collections import deque
from copy import deepcopy
from typing import Any


class Session:
    """Keep complete user turns in memory, including paired tool messages."""

    def __init__(self, max_turns: int = 6):
        if max_turns < 1:
            raise ValueError("max_turns must be positive")
        self._turns: deque[list[dict[str, Any]]] = deque(maxlen=max_turns)

    def history(self) -> list[dict[str, Any]]:
        return deepcopy([message for turn in self._turns for message in turn])

    @property
    def max_turns(self) -> int:
        return self._turns.maxlen

    def export_turns(self) -> list[list[dict[str, Any]]]:
        return deepcopy(list(self._turns))

    def restore(self, turns: list[list[dict[str, Any]]]) -> None:
        self._turns = deque(deepcopy(turns), maxlen=self.max_turns)

    def add_turn(self, messages: list[dict[str, Any]]) -> None:
        self._turns.append(deepcopy(messages))

    def clear(self) -> None:
        self._turns.clear()
