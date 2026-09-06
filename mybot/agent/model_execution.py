"""Model request boundary for the AgentLoop.

The executor owns only context preparation, OpenAI-compatible requests,
timeouts/retries, and LLM trace bookkeeping.  Task and Tool orchestration stay
in AgentLoop.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from openai import APITimeoutError


MAX_RATE_LIMIT_RETRIES_HARD_LIMIT = 10
DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS = 60.0


@dataclass(slots=True)
class ModelTurnResult:
    message: Any | None = None
    content: str = ""
    finish_reason: str | None = None
    error: str | None = None
    error_reason: str | None = None


class ModelExecutor:
    """Execute one model turn and attach all request-level trace data."""

    def __init__(self, *, client: Any, config: Any, context: Any, tracer: Any):
        self.client = client
        self.config = config
        self.context = context
        self.tracer = tracer

    async def request(
        self,
        messages: list[dict],
        *,
        step_id: str | None = None,
        task_anchor: str = "",
        tool_definitions: list[dict] | None = None,
    ) -> ModelTurnResult:
        retry_count = 0
        retry_limit = self._effective_rate_limit_retries()
        timeout = self._effective_request_timeout_seconds()
        model_messages = messages
        context_metadata: dict[str, Any] = {}
        if hasattr(self.context, "prepare_messages"):
            model_messages, context_metadata = self.context.prepare_messages(
                messages,
                task_anchor=task_anchor,
            )

        while True:
            llm_trace = None
            if step_id:
                llm_trace = self.tracer.start_llm_call(
                    step_id=step_id,
                    model=self.config.model,
                    provider=getattr(self.config, "provider", ""),
                    message_count=len(messages),
                    retry_count=retry_count,
                )
                if context_metadata:
                    llm_trace.metadata.update(context_metadata)
            try:
                response = await asyncio.wait_for(
                    self.client.chat.completions.create(
                        model=self.config.model,
                        messages=model_messages,
                        tools=tool_definitions or None,
                        temperature=0.1,
                        max_tokens=self.config.max_completion_tokens,
                    ),
                    timeout=timeout,
                )
            except (TimeoutError, APITimeoutError):
                error = self.timeout_error(timeout)
                if llm_trace:
                    self.tracer.finish_llm_call(llm_trace, error=error)
                return ModelTurnResult(
                    error=error,
                    error_reason="llm_timeout",
                )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                if llm_trace:
                    self.tracer.finish_llm_call(llm_trace, error=error)
                if self.is_rate_limit_error(exc) and retry_count < retry_limit:
                    retry_count += 1
                    await asyncio.sleep(60)
                    continue
                return ModelTurnResult(error=error, error_reason="llm_error")

            choice = response.choices[0]
            message = choice.message
            finish_reason = choice.finish_reason
            content = (message.content or "").strip()
            usage = getattr(response, "usage", None)
            if llm_trace:
                self.tracer.finish_llm_call(
                    llm_trace,
                    finish_reason=finish_reason,
                    input_tokens=self.usage_value(usage, "prompt_tokens"),
                    output_tokens=self.usage_value(usage, "completion_tokens"),
                    total_tokens=self.usage_value(usage, "total_tokens"),
                )
            return ModelTurnResult(
                message=message,
                content=content,
                finish_reason=finish_reason,
            )

    def _effective_rate_limit_retries(self) -> int:
        try:
            value = int(getattr(self.config, "rate_limit_retries", 0))
        except (TypeError, ValueError):
            value = 0
        return max(0, min(value, MAX_RATE_LIMIT_RETRIES_HARD_LIMIT))

    def _effective_request_timeout_seconds(self) -> float:
        raw_timeout = getattr(
            self.config,
            "request_timeout_seconds",
            DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
        )
        try:
            timeout = float(raw_timeout)
        except (TypeError, ValueError):
            timeout = DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS
        return timeout if timeout > 0 else DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS

    @staticmethod
    def timeout_error(timeout_seconds: float) -> str:
        return f"LLM request timeout after {timeout_seconds:g}s"

    @staticmethod
    def is_rate_limit_error(exc: Exception) -> bool:
        text = f"{type(exc).__name__}: {exc}"
        return (
            "RateLimitError" in text
            or "429" in text
            or "TPM limit reached" in text
        )

    @staticmethod
    def usage_value(usage: Any, name: str) -> int | None:
        if usage is None:
            return None
        value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        return value if isinstance(value, int) else None
