from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from ..agent.loop import AgentLoop
from ..tools.result import BrowserResult, ToolResult
from ..tracing import AgentTracer
from .models import EvalCase


class FakeCompletions:
    def __init__(self, case: EvalCase):
        self._tools = list(case.metadata.get("fake_tools", []))
        configured_batches = case.metadata.get("fake_tool_batches")
        self._tool_batches = (
            [list(batch) for batch in configured_batches]
            if configured_batches is not None
            else [[tool] for tool in self._tools]
        )
        self._final_output = str(case.metadata.get("fake_output", "done"))
        self._empty_responses = int(
            case.metadata.get("fake_empty_responses", 0)
        )
        self._index = 0
        self.requests: list[dict[str, Any]] = []

    async def create(self, **kwargs) -> SimpleNamespace:
        self.requests.append(dict(kwargs))
        usage = SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
        if self._index < self._empty_responses:
            self._index += 1
            message = SimpleNamespace(content=None, tool_calls=None)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(message=message, finish_reason="stop")
                ],
                usage=usage,
            )

        tool_index = self._index - self._empty_responses
        self._index += 1
        if tool_index < len(self._tool_batches):
            batch = self._tool_batches[tool_index]
            tool_calls = [
                SimpleNamespace(
                    id=f"fake_call_{tool_index + 1:03d}_{index + 1:02d}",
                    function=SimpleNamespace(
                        name=str(tool["name"]),
                        arguments=json.dumps(
                            tool.get("arguments", {}),
                            ensure_ascii=False,
                        ),
                    ),
                )
                for index, tool in enumerate(batch)
            ]
            message = SimpleNamespace(content=None, tool_calls=tool_calls)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=message,
                        finish_reason="tool_calls",
                    )
                ],
                usage=usage,
            )

        message = SimpleNamespace(content=self._final_output, tool_calls=None)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")],
            usage=usage,
        )


class FakeToolRegistry:
    def __init__(self, tool_script: list[dict[str, Any]]):
        self._script = tool_script
        self._execute_index = 0
        self.executed_calls: list[tuple[str, dict[str, Any]]] = []

    @property
    def execution_count(self) -> int:
        return self._execute_index

    def get_definitions(self) -> list[dict]:
        names = list(dict.fromkeys(str(tool["name"]) for tool in self._script))
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": "Deterministic fake eval tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
            for name in names
        ]

    def get_runtime_metadata(self, name: str) -> dict[str, Any]:
        for tool in self._script:
            if str(tool["name"]) == name:
                return dict(tool.get("runtime_metadata", {}))
        return {}

    async def execute(self, name: str, params: dict) -> ToolResult:
        if self._execute_index >= len(self._script):
            return ToolResult(success=False, error="fake tool script exhausted")
        scripted = self._script[self._execute_index]
        self._execute_index += 1
        self.executed_calls.append((name, dict(params)))
        if str(scripted["name"]) != name:
            return ToolResult(
                success=False,
                error=f"expected fake tool {scripted['name']}, received {name}",
            )

        success = bool(scripted.get("success", True))
        output = str(scripted.get("output", "ok"))
        error = scripted.get("error")
        metadata = dict(scripted.get("result_metadata", {}))
        if name.startswith("browser_"):
            default_session = (
                "local_browser" if name == "browser_attach" else "managed_browser"
            )
            return BrowserResult(
                success=success,
                output=output,
                error=str(error) if error else None,
                metadata=metadata,
                action=name.removeprefix("browser_"),
                session=str(params.get("session", default_session)),
            )
        return ToolResult(
            success=success,
            output=output,
            error=str(error) if error else None,
            metadata=metadata,
        )


def build_fake_agent(case: EvalCase) -> AgentLoop:
    tool_script = list(case.metadata.get("fake_tools", []))
    minimum_steps = len(tool_script) + int(
        case.metadata.get("fake_empty_responses", 0)
    ) + 1
    configured_steps = max(case.max_steps or 10, minimum_steps)
    config = SimpleNamespace(
        model="fake-eval-model",
        provider="fake",
        max_completion_tokens=100,
        max_react_steps=configured_steps,
        rate_limit_retries=0,
        request_timeout_seconds=60,
        show_internal_process=False,
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=FakeCompletions(case),
        )
    )
    return AgentLoop(
        client=client,
        config=config,
        bus=None,
        tools=FakeToolRegistry(tool_script),
        context=None,
        sessions=None,
        tracer=AgentTracer(),
    )
