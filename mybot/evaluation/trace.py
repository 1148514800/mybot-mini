from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

from ..agent.loop import AgentLoop
from ..agent.context_manager import ContextManager


class RequestLimitError(RuntimeError):
    pass


class Trace:
    """Metadata only: no prompts, arguments, response bodies or error messages."""
    def __init__(self):
        self.events = []
        self.error = None
        self.finish_reason = None
        self.skills = []
        self.usage = []
        self.names = set()
        self.paths = set()

    def tool(self, name, arguments, result, duration):
        safe_name = name if name in self.names else "<unknown>"
        try:
            params = json.loads(arguments) if isinstance(arguments, str) else arguments
        except (ValueError, TypeError):
            params = {}
        params = params if isinstance(params, dict) else {}
        target = params.get("path")
        safe_target = target if isinstance(target, str) and target in self.paths else None
        self.events.append({"event": "tool", "name": safe_name, "success": result.success,
                            "output_chars": len(result.output), "duration_seconds": duration,
                            "error": None if result.success else "tool_failed", "fixture_path": safe_target})
        if name == "load_skill" and result.success:
            self.skills.append(params["name"])

    def metrics(self):
        tools = [e for e in self.events if e["event"] == "tool"]
        requests = [e for e in self.events if e["event"] == "llm_request"]
        return {"tool_calls": len(tools), "tool_failures": sum(not e["success"] for e in tools),
                "llm_requests": len(requests), "skill_selected": list(dict.fromkeys(self.skills)),
                "input_tokens": self.tokens("prompt_tokens"), "output_tokens": self.tokens("completion_tokens")}

    def tokens(self, key):
        values = [getattr(usage, key, None) for usage in self.usage]
        if not values or len(values) != sum(e["event"] == "llm_request" for e in self.events):
            return None
        return sum(values) if all(type(v) is int and v >= 0 for v in values) else None


class TracedClient:
    def __init__(self, client, trace, budget):
        self.client, self.trace, self.budget = client, trace, budget
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        if self.budget["used"] >= self.budget["maximum"]:
            self.trace.error = "model_request_limit"
            raise RequestLimitError()
        self.budget["used"] += 1
        self.trace.events.append({"event": "llm_request",
                                 "request_chars": ContextManager.count(kwargs["messages"], kwargs.get("tools")),
                                 "messages": len(kwargs["messages"]),
                                 "tool_result_clipped": any(ContextManager.marker in (m.get("content") or "") for m in kwargs["messages"])})
        start = time.perf_counter()
        try:
            response = await self.client.chat.completions.create(**kwargs)
        except BaseException as exc:
            # Never persist SDK errors: they can contain URLs, payloads or secrets.
            self.trace.error = "llm_timeout_or_cancelled" if isinstance(exc, (TimeoutError, asyncio.CancelledError)) else "llm_error"
            self.trace.events.append({"event": "llm_error", "duration_seconds": time.perf_counter() - start})
            raise
        self.trace.usage.append(getattr(response, "usage", None))
        message = response.choices[0].message
        self.trace.events.append({"event": "llm_response", "output_chars": len(message.content or ""),
                                 "tool_calls": len(message.tool_calls or []), "duration_seconds": time.perf_counter() - start})
        return response


class TracedAgent(AgentLoop):
    def __init__(self, *args, trace, **kwargs):
        self.trace = trace
        super().__init__(*args, **kwargs)
        self.trace.names = {item["function"]["name"] for item in self.tools.get_definitions()}

    async def _execute(self, name, raw_arguments):
        start = time.perf_counter()
        result = await super()._execute(name, raw_arguments)
        self.trace.tool(name, raw_arguments, result, time.perf_counter() - start)
        return result

    def _finish_turn(self, messages, turn_start, reply, reason=""):
        self.trace.finish_reason = "react_limit" if reason else "finished"
        return super()._finish_turn(messages, turn_start, reply, reason)
