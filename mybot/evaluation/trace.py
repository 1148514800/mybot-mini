from __future__ import annotations

import asyncio
import json
import hashlib
from collections import Counter
import time
from types import SimpleNamespace

from ..agent.loop import AgentLoop
from ..agent.context_manager import ContextManager


class RequestLimitError(RuntimeError):
    pass


PLAN_ERRORS = {
    "No active plan for this task":"plan_missing",
    "step must be a valid 1-based integer":"plan_invalid_step",
    "Invalid target status":"plan_invalid_status",
    "Start only the next pending step in order":"plan_step_order",
    "Only an in_progress step can finish":"plan_not_in_progress",
    "Step is unverified: no successful execution result":"plan_unverified",
    "A task can create only one plan; replanning is not supported":"plan_recreation",
}


def error_category(name, result):
    if result.success:
        return None
    return PLAN_ERRORS.get(result.error,"other_tool_error") if name in ("create_plan","update_plan") else "other_tool_error"


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
        self.workspace = None
        self.reads = Counter()
        self.plan_created = False
        self.pre_plan_files = 0

    def tool(self, name, arguments, result, duration):
        safe_name = name if name in self.names else "<unknown>"
        try:
            params = json.loads(arguments) if isinstance(arguments, str) else arguments
        except (ValueError, TypeError):
            params = {}
        params = params if isinstance(params, dict) else {}
        target = params.get("path")
        safe_target = None
        if isinstance(target,str) and self.workspace is not None and name in ("read_file","write_file","list_files"):
            try:
                normalized = (self.workspace/target).resolve()
            except (OSError,ValueError,RuntimeError):
                normalized = None
            if normalized is not None and normalized.is_relative_to(self.workspace):
                relative = normalized.relative_to(self.workspace).as_posix()
                safe_target = relative if relative in self.paths else None
                if name == "read_file":
                    self.reads[hashlib.sha256(relative.encode()).hexdigest()] += 1
        if name in ("read_file","write_file","list_files") and not self.plan_created:
            self.pre_plan_files += 1
        if name == "create_plan" and result.success:
            self.plan_created = True
        self.events.append({"event": "tool", "name": safe_name, "success": result.success,
                            "output_chars": len(result.output), "duration_seconds": duration,
                            "error": error_category(name,result), "fixture_path": safe_target,
                            "skill_name":params.get("name") if result.success and name in ("load_skill","read_skill_reference") else None})
        if name == "load_skill" and result.success:
            self.skills.append(params["name"])

    def metrics(self):
        tools = [e for e in self.events if e["event"] == "tool"]
        requests = [e for e in self.events if e["event"] == "llm_request"]
        categories = Counter(e["error"] for e in tools if e["name"] in ("create_plan","update_plan") and not e["success"])
        input_tokens, output_tokens = self.tokens("prompt_tokens"), self.tokens("completion_tokens")
        with_skill = [i for i,e in enumerate(requests) if e.get("skill_content_chars",0)]
        skill_tokens = {}
        for key in ("prompt_tokens","completion_tokens"):
            values = [getattr(self.usage[i],key,None) for i in with_skill if i<len(self.usage)]
            skill_tokens[key] = sum(values) if len(values)==len(with_skill) and all(type(v) is int for v in values) else None
        return {"tool_calls":len(tools),"tool_failures":sum(not e["success"] for e in tools),
                "llm_requests":len(requests),"skill_selected":list(dict.fromkeys(self.skills)),
                "input_tokens":input_tokens,"output_tokens":output_tokens,
                "total_tokens":input_tokens+output_tokens if input_tokens is not None and output_tokens is not None else None,
                "planning_failure_categories":dict(categories),"planning_tool_failures":sum(categories.values()),
                "file_tools_before_plan":self.pre_plan_files,"duplicate_reads":sum(max(0,n-1) for n in self.reads.values()),
                "skill_usage":{"loaded":bool(self.skills),"selected":list(dict.fromkeys(self.skills)),
                               "load_calls":sum(e["name"]=="load_skill" for e in tools),
                               "successful_loads":len(self.skills),
                               "reference_calls":sum(e["name"]=="read_skill_reference" for e in tools),
                               "successful_references":sum(e["name"]=="read_skill_reference" and e["success"] for e in tools),
                               "skill_response_batches":sum(e.get("skill_calls",0)>0 for e in self.events if e["event"]=="llm_response"),
                               "load_response_batches":sum(e.get("load_skill_calls",0)>0 for e in self.events if e["event"]=="llm_response"),
                               "requests_with_skill_content":len(with_skill),
                               "skill_content_chars_in_requests":sum(e.get("skill_content_chars",0) for e in requests),
                               "input_tokens_with_skill_content":skill_tokens["prompt_tokens"],
                               "output_tokens_with_skill_content":skill_tokens["completion_tokens"],
                               "extra_llm_requests":None,"extra_tokens":None}}

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
        skill_ids = {call["id"] for m in kwargs["messages"] for call in m.get("tool_calls") or []
                     if call["function"]["name"] in ("load_skill","read_skill_reference")}
        skill_chars = sum(len(m.get("content") or "") for m in kwargs["messages"] if m.get("tool_call_id") in skill_ids)
        self.trace.events.append({"event": "llm_request",
                                 "request_chars": ContextManager.count(kwargs["messages"], kwargs.get("tools")),
                                 "messages": len(kwargs["messages"]), "skill_content_chars":skill_chars,
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
        choice = response.choices[0]
        finish = getattr(choice,'finish_reason',None)
        finish = finish if finish in ('stop','tool_calls','length','content_filter','function_call') else 'unknown'
        message = choice.message
        self.trace.events.append({"event": "llm_response", "finish_reason":finish,"output_chars": len(message.content or ""),
                                 "tool_calls": len(message.tool_calls or []),
                                 "load_skill_calls":sum(c.function.name=="load_skill" for c in message.tool_calls or []),
                                 "skill_calls":sum(c.function.name in ("load_skill","read_skill_reference") for c in message.tool_calls or []), "duration_seconds": time.perf_counter() - start})
        return response


class TracedAgent(AgentLoop):
    def __init__(self, *args, trace, **kwargs):
        self.trace = trace
        super().__init__(*args, **kwargs)
        self.trace.workspace = self.config.workspace.resolve()
        self.trace.names = {item["function"]["name"] for item in self.tools.get_definitions()}

    async def _execute(self, name, raw_arguments):
        start = time.perf_counter()
        result = await super()._execute(name, raw_arguments)
        self.trace.tool(name, raw_arguments, result, time.perf_counter() - start)
        return result

    def _finish_turn(self, messages, turn_start, reply, reason=""):
        self.trace.finish_reason = "react_limit" if reason else "finished"
        return super()._finish_turn(messages, turn_start, reply, reason)
