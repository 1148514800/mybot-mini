"""Opt-in production-like end-to-end evaluations.

The regular eval runner intentionally remains deterministic and offline.  This
module is the separate entry point for tests that call a real OpenAI-compatible
provider and, optionally, a real browser.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from ..agent.context import ContextBuilder
from ..agent.loop import AgentLoop
from ..core.config import GatewayConfig, build_client
from ..storage.checkpoints.store import ActiveTaskCheckpointStore
from ..storage.memory import MemoryManager
from ..storage.session import SessionManager
from ..tools import build_default_tool_registry
from ..tracing import AgentRunTrace, AgentTracer, redact_text
from ..workspace import init_instructions, init_workspace


LIVE_OPT_IN = "MYBOT_RUN_LIVE_E2E"
BROWSER_OPT_IN = "MYBOT_RUN_BROWSER_LIVE_E2E"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


@dataclass(slots=True)
class LiveEvalCase:
    """A named live workflow.  ``run`` owns its temporary workspace."""

    name: str
    run: Callable[["LiveEvalContext"], Awaitable["LiveEvalResult"]]
    browser: bool = False


@dataclass(slots=True)
class LiveEvalResult:
    name: str
    status: str
    duration_ms: float = 0.0
    task_id: str | None = None
    run_id: str | None = None
    provider: str = ""
    model: str = ""
    tool_calls: list[str] = field(default_factory=list)
    llm_calls: int = 0
    final_task_status: str | None = None
    failure_reason: str | None = None
    context_stats: list[dict[str, Any]] = field(default_factory=list)
    browser_completion_evidence: list[dict[str, Any]] = field(default_factory=list)
    traces: list[AgentRunTrace] = field(default_factory=list, repr=False)

    @classmethod
    def skipped(cls, name: str, reason: str) -> "LiveEvalResult":
        return cls(name=name, status="skip", failure_reason=reason)

    def public_dict(self) -> dict[str, Any]:
        """Return report-safe fields without raw arguments or trace payloads."""
        return {
            "name": self.name,
            "status": self.status,
            "duration": self.duration_ms,
            "duration_ms": self.duration_ms,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "provider": self.provider,
            "model": self.model,
            "tool_calls": list(self.tool_calls),
            "llm_calls": self.llm_calls,
            "final_task_status": self.final_task_status,
            "failure_reason": self.failure_reason,
            "context_stats": list(self.context_stats),
            "browser_completion_evidence": list(
                self.browser_completion_evidence
            ),
        }


@dataclass(slots=True)
class LiveEvalContext:
    config: GatewayConfig
    workspace: Path
    key: str
    base_url: str | None
    client: Any
    agent: AgentLoop

    async def close(self) -> None:
        await self.client.close()


def _enabled(name: str, environ: dict[str, str] | None = None) -> bool:
    values = environ if environ is not None else os.environ
    return values.get(name, "").strip().lower() in _TRUE_VALUES


def _api_settings(environ: dict[str, str] | None = None) -> tuple[str | None, str | None, str | None, str]:
    values = environ if environ is not None else os.environ
    configured = GatewayConfig() if environ is None else None
    key = values.get("MYBOT_LIVE_API_KEY") or values.get("OPENAI_API_KEY") or (configured.api_key if configured else None)
    base_url = values.get("MYBOT_LIVE_BASE_URL") or values.get("OPENAI_BASE_URL") or (configured.base_url if configured else None)
    model = values.get("MYBOT_MODEL") or values.get("MYBOT_LIVE_MODEL") or (configured.model if configured else "gpt-4.1-mini")
    provider = values.get("MYBOT_LIVE_PROVIDER") or (configured.provider if configured else "openai-compatible")
    normalized_key = key.strip() if key else None
    if normalized_key and normalized_key.lower() in {
        "your-api-key",
        "replace-me",
        "替换为你的 api key",
    }:
        normalized_key = None
    return (normalized_key, base_url.strip() if base_url else None, model.strip() if model else None, provider.strip())


def _browser_prerequisite() -> str | None:
    executable = shutil.which("playwright-cli")
    if not executable:
        return "environment/network: playwright-cli is not available"
    try:
        completed = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"environment/network: playwright-cli check failed ({type(exc).__name__})"
    if completed.returncode != 0:
        return "environment/network: playwright-cli version check failed"
    return None


def _failure_category(reason: str, traces: list[AgentRunTrace]) -> str:
    lowered = reason.lower()
    if any(token in lowered for token in ("apiconnection", "apitimeout", "timeout", "connection", "401", "429", "authentication", "unauthorized", "rate limit", "network")):
        return "environment/network"
    if any(call.success is False for trace in traces for call in trace.tool_calls):
        return "tool failure"
    if any(token in lowered for token in ("expected tool", "model did not", "model behavior")):
        return "model behavior"
    if any(token in lowered for token in ("task status", "checkpoint", "sender", "runtime", "startup")):
        return "runtime correctness"
    return "assertion"


def _failure(reason: str, traces: list[AgentRunTrace]) -> str:
    return f"{_failure_category(reason, traces)}: {redact_text(reason)}"


def _result(
    name: str,
    started: float,
    config: GatewayConfig,
    traces: list[AgentRunTrace],
    *,
    status: str = "pass",
    failure_reason: str | None = None,
) -> LiveEvalResult:
    final = traces[-1] if traces else None
    task_ids = [trace.task_id for trace in traces if trace.task_id]
    tool_calls = [
        call.tool_name for trace in traces for call in trace.tool_calls
    ]
    context_stats = [
        {
            key: value
            for key, value in call.metadata.items()
            if key in {
                "context_chars_before",
                "context_chars_after",
                "context_truncated",
                "context_budget_overflow",
            }
        }
        for trace in traces
        for call in trace.llm_calls
        if any(
            key in call.metadata
            for key in {
                "context_chars_before",
                "context_chars_after",
                "context_truncated",
                "context_budget_overflow",
            }
        )
    ]
    browser_evidence = [
        {
            key: value
            for key, value in call.metadata.items()
            if key in {"completion_evidence", "postcondition_met", "browser_completion_state"}
        }
        for trace in traces
        for call in trace.tool_calls
        if any(
            key in call.metadata
            for key in {"completion_evidence", "postcondition_met", "browser_completion_state"}
        )
    ]
    if status == "fail" and traces:
        trace_errors = [
            trace.error
            for trace in traces
            if trace.error
        ]
        if trace_errors:
            failure_reason = f"{_failure(trace_errors[-1], traces)}; {failure_reason or 'assertion failed'}"
    return LiveEvalResult(
        name=name,
        status=status,
        duration_ms=(time.perf_counter() - started) * 1000,
        task_id=task_ids[-1] if task_ids else None,
        run_id=final.run_id if final else None,
        provider=config.provider,
        model=config.model,
        tool_calls=tool_calls,
        llm_calls=sum(len(trace.llm_calls) for trace in traces),
        final_task_status=final.task_status if final else None,
        failure_reason=failure_reason,
        context_stats=context_stats,
        browser_completion_evidence=browser_evidence,
        traces=traces,
    )


async def _make_context(
    workspace: Path,
    *,
    key: str,
    base_url: str | None,
    model: str,
    provider: str = "openai-compatible",
    max_react_steps: int = 10,
    max_context_chars: int = 60_000,
    max_tool_result_chars: int = 8_000,
) -> LiveEvalContext:
    init_instructions(workspace / "instructions")
    init_workspace(workspace)
    config = GatewayConfig(
        provider=provider,
        model=model,
        api_key=key,
        base_url=base_url,
        workspace=workspace,
        trace_dir=None,
        max_react_steps=max_react_steps,
        max_context_chars=max_context_chars,
        max_tool_result_chars=max_tool_result_chars,
        checkpoint_enabled=True,
        show_internal_process=False,
        rate_limit_retries=0,
        request_timeout_seconds=float(os.environ.get("MYBOT_LIVE_TIMEOUT_SECONDS", "60")),
    )
    memory = MemoryManager(workspace)
    tools = build_default_tool_registry(workspace, memory_manager=memory)
    client = build_client(config)
    agent = AgentLoop(
        client=client,
        config=config,
        bus=None,
        tools=tools,
        context=ContextBuilder(
            workspace,
            memory_manager=memory,
            max_context_chars=max_context_chars,
            max_tool_result_chars=max_tool_result_chars,
        ),
        sessions=SessionManager(workspace),
        tracer=AgentTracer(),
        checkpoint_store=ActiveTaskCheckpointStore(workspace),
    )
    return LiveEvalContext(config, workspace, key, base_url, client, agent)


async def _run_basic(context: LiveEvalContext) -> LiveEvalResult:
    name = "real_llm_basic"
    started = time.perf_counter()
    traces: list[AgentRunTrace] = []
    try:
        output, trace = await context.agent.run_traced(
            "Answer in one short sentence: what is 2 + 2? Do not call any tools.",
            [{"role": "user", "content": "What is 2 + 2?"}],
            session_key="live:basic",
            requester_sender_id="live-sender",
        )
        traces.append(trace)
        reasons = []
        if trace.status != "success":
            reasons.append(f"run status {trace.status}")
        if trace.task_status != "completed":
            reasons.append(f"task status {trace.task_status}")
        if not output.strip():
            reasons.append("final output is empty")
        if not trace.llm_calls:
            reasons.append("no LLM call recorded")
        if trace.tool_calls:
            reasons.append("model called a tool for the direct task")
        if len(trace.llm_calls) > 2:
            reasons.append(f"direct task used {len(trace.llm_calls)} LLM calls")
        if any(call.finished_at is None for call in trace.llm_calls) or any(call.finished_at is None for call in trace.tool_calls):
            reasons.append("trace contains unfinished calls")
        if reasons:
            return _result(name, started, context.config, traces, status="fail", failure_reason=_failure("; ".join(reasons), traces))
        return _result(name, started, context.config, traces)
    except Exception as exc:
        return _result(name, started, context.config, traces, status="fail", failure_reason=_failure(f"{type(exc).__name__}: {exc}", traces))


async def _run_read_file(context: LiveEvalContext) -> LiveEvalResult:
    name = "read_file_tool"
    started = time.perf_counter()
    traces: list[AgentRunTrace] = []
    marker = "MYBOT_LIVE_READ_MARKER_7F3"
    (context.workspace / "known.txt").write_text(
        f"The required value is {marker}.", encoding="utf-8"
    )
    try:
        output, trace = await context.agent.run_traced(
            "Use the read_file tool to read known.txt. Then answer with the exact required value from the file. Do not guess and do not use another tool.",
            [{"role": "user", "content": "Read known.txt and report its required value."}],
            session_key="live:read-file",
            requester_sender_id="live-sender",
        )
        traces.append(trace)
        reads = [call for call in trace.tool_calls if call.tool_name == "read_file"]
        reasons = []
        if trace.status != "success" or trace.task_status != "completed":
            reasons.append(f"task ended as {trace.status}/{trace.task_status}")
        if not reads:
            reasons.append("model behavior did not select read_file")
        elif len(reads) != 1:
            reasons.append(f"read_file called {len(reads)} times")
        elif not reads[0].success:
            reasons.append("read_file returned failure")
        if len(trace.llm_calls) < 2:
            reasons.append("tool workflow did not return to the model")
        if marker not in output:
            reasons.append("final output does not contain the known marker")
        if reasons:
            return _result(name, started, context.config, traces, status="fail", failure_reason=_failure("; ".join(reasons), traces))
        return _result(name, started, context.config, traces)
    except Exception as exc:
        return _result(name, started, context.config, traces, status="fail", failure_reason=_failure(f"{type(exc).__name__}: {exc}", traces))


async def _run_approval(context: LiveEvalContext, *, name: str, restart: bool = False) -> LiveEvalResult:
    started = time.perf_counter()
    traces: list[AgentRunTrace] = []
    session = f"live:{'restart' if restart else 'approval'}"
    sender = "live-original-sender"
    path = "instructions/approved-output.txt"
    content = "MYBOT_LIVE_APPROVED_CONTENT"
    try:
        prompt = (
            f"Use the write_file tool to create {path} with exactly this content: "
            f"{content}. You must use the tool; do not merely describe the action."
        )
        first_context = context
        output, trace = await first_context.agent.run_traced(
            prompt,
            [{"role": "user", "content": prompt}],
            session_key=session,
            requester_sender_id=sender,
        )
        traces.append(trace)
        pending = first_context.agent.approvals.get(session)
        if trace.status != "awaiting_confirmation" or trace.task_status != "waiting_approval" or pending is None:
            return _result(name, started, context.config, traces, status="fail", failure_reason=_failure("model behavior did not produce the expected write_file approval", traces))
        if (context.workspace / path).exists():
            return _result(name, started, context.config, traces, status="fail", failure_reason=_failure("write_file produced a side effect before approval", traces))
        if restart:
            await first_context.close()
            restarted = await _make_context(
                context.workspace,
                key=context.key,
                base_url=context.base_url,
                model=context.config.model,
                max_react_steps=context.config.max_react_steps,
                max_context_chars=context.config.max_context_chars,
                max_tool_result_chars=context.config.max_tool_result_chars,
            )
            context = restarted
            pending = context.agent.approvals.get(session)
            if context.agent.tracer.get_current_run() is not None or pending is None:
                return _result(name, started, context.config, traces, status="fail", failure_reason=_failure("startup called the model or failed to restore approval", traces))
            if (context.workspace / path).exists():
                return _result(name, started, context.config, traces, status="fail", failure_reason=_failure("startup produced a side effect", traces))
        _, wrong_trace = await context.agent.resume_pending(session, "确认", "wrong-sender")
        traces.append(wrong_trace)
        if (context.workspace / path).exists():
            return _result(name, started, context.config, traces, status="fail", failure_reason=_failure("wrong sender executed the side effect", traces))
        if context.agent.approvals.get(session) is None:
            return _result(name, started, context.config, traces, status="fail", failure_reason=_failure("wrong sender consumed the pending approval", traces))
        output, approved_trace = await context.agent.resume_pending(session, "确认", sender)
        traces.append(approved_trace)
        target = context.workspace / path
        writes = [
            call for trace_item in traces
            for call in trace_item.tool_calls
            if call.tool_name == "write_file" and call.success
        ]
        reasons = []
        if not target.exists() or target.read_text(encoding="utf-8") != content:
            reasons.append("approved file content is incorrect")
        if len(writes) != 1:
            reasons.append(f"write_file executed {len(writes)} times")
        if approved_trace.task_status != "completed":
            reasons.append(f"final task status {approved_trace.task_status}")
        if not any(call.metadata.get("policy_decision") for item in traces for call in item.tool_calls if call.tool_name == "write_file"):
            reasons.append("write_file trace has no ToolPolicy decision")
        if context.agent.checkpoint_store and context.agent.checkpoint_store.active_count() != 0:
            reasons.append("terminal task left an active checkpoint")
        if reasons:
            return _result(name, started, context.config, traces, status="fail", failure_reason=_failure("; ".join(reasons), traces))
        return _result(name, started, context.config, traces)
    except Exception as exc:
        return _result(name, started, context.config, traces, status="fail", failure_reason=_failure(f"{type(exc).__name__}: {exc}", traces))
    finally:
        if restart and context is not None:
            await context.close()


async def _run_approval_side_effect(context: LiveEvalContext) -> LiveEvalResult:
    return await _run_approval(context, name="approval_side_effect")


async def _run_restart_recovery(context: LiveEvalContext) -> LiveEvalResult:
    name = "restart_recovery"
    started = time.perf_counter()
    traces: list[AgentRunTrace] = []
    session = "live:restart"
    sender = "live-original-sender"
    path = "instructions/restart-output.txt"
    content = "MYBOT_LIVE_RESTART_CONTENT"
    try:
        prompt = (
            "Before taking any file action, ask me one clarification question using request_user_input "
            "about the exact content for restart-output.txt. Do not call write_file until I answer."
        )
        _, trace = await context.agent.run_traced(
            prompt,
            [{"role": "user", "content": prompt}],
            session_key=session,
            requester_sender_id=sender,
        )
        traces.append(trace)
        pending = context.agent.clarifications.get(session)
        if trace.status != "awaiting_clarification" or trace.task_status != "waiting_clarification" or pending is None:
            return _result(name, started, context.config, traces, status="fail", failure_reason=_failure("model behavior did not produce the expected clarification checkpoint", traces))
        if (context.workspace / path).exists() or context.agent.checkpoint_store.active_count() != 1:
            return _result(name, started, context.config, traces, status="fail", failure_reason=_failure("clarification checkpoint or pre-action state is invalid", traces))

        await context.close()
        restarted = await _make_context(
            context.workspace,
            key=context.key,
            base_url=context.base_url,
            model=context.config.model,
            max_react_steps=context.config.max_react_steps,
            max_context_chars=context.config.max_context_chars,
            max_tool_result_chars=context.config.max_tool_result_chars,
        )
        context = restarted
        pending = context.agent.clarifications.get(session)
        if context.agent.tracer.get_current_run() is not None or pending is None:
            return _result(name, started, context.config, traces, status="fail", failure_reason=_failure("startup called the model or failed to restore clarification", traces))
        if (context.workspace / path).exists():
            return _result(name, started, context.config, traces, status="fail", failure_reason=_failure("startup produced a side effect", traces))

        _, wrong_trace = await context.agent.resume_clarification(
            session,
            f"Write exactly {content} to {path}.",
            "wrong-sender",
        )
        traces.append(wrong_trace)
        if context.agent.clarifications.get(session) is None or (context.workspace / path).exists():
            return _result(name, started, context.config, traces, status="fail", failure_reason=_failure("wrong sender consumed clarification or produced a side effect", traces))

        _, answered_trace = await context.agent.resume_clarification(
            session,
            f"Write exactly {content} to {path}.",
            sender,
        )
        traces.append(answered_trace)
        approval = context.agent.approvals.get(session)
        if approval is None or answered_trace.status != "awaiting_confirmation":
            return _result(name, started, context.config, traces, status="fail", failure_reason=_failure("model behavior did not request approval after restart recovery", traces))
        output, approved_trace = await context.agent.resume_pending(session, "确认", sender)
        traces.append(approved_trace)
        target = context.workspace / path
        writes = [
            call for trace_item in traces
            for call in trace_item.tool_calls
            if call.tool_name == "write_file" and call.success
        ]
        reasons = []
        if not target.exists() or target.read_text(encoding="utf-8") != content:
            reasons.append("recovered approval did not produce the expected file")
        if len(writes) != 1:
            reasons.append(f"write_file executed {len(writes)} times")
        if approved_trace.task_status != "completed":
            reasons.append(f"final task status {approved_trace.task_status}")
        if context.agent.checkpoint_store.active_count() != 0:
            reasons.append("terminal task left an active checkpoint")
        if reasons:
            return _result(name, started, context.config, traces, status="fail", failure_reason=_failure("; ".join(reasons), traces))
        return _result(name, started, context.config, traces)
    except Exception as exc:
        return _result(name, started, context.config, traces, status="fail", failure_reason=_failure(f"{type(exc).__name__}: {exc}", traces))
    finally:
        await context.close()


async def _run_context_budget(context: LiveEvalContext) -> LiveEvalResult:
    name = "context_budget"
    started = time.perf_counter()
    traces: list[AgentRunTrace] = []
    markers = ["MYBOT_CONTEXT_A", "MYBOT_CONTEXT_B", "MYBOT_CONTEXT_C"]
    for index, marker in enumerate(markers):
        (context.workspace / f"context-{index}.txt").write_text(
            (marker + " ") * 500, encoding="utf-8"
        )
    try:
        prompt = (
            "In one assistant tool-call batch, call read_file exactly once for each of context-0.txt, context-1.txt, and context-2.txt. "
            "Do not call any path twice. After the three tool results arrive, answer with all three markers and do not call another tool."
        )
        output, trace = await context.agent.run_traced(
            prompt,
            [{"role": "user", "content": prompt}],
            session_key="live:context-budget",
            requester_sender_id="live-sender",
        )
        traces.append(trace)
        stats = [stat for item in traces for stat in _trace_context_stats(item)]
        reasons = []
        if trace.status != "success" or trace.task_status != "completed":
            reasons.append(f"task ended as {trace.status}/{trace.task_status}")
        if not all(marker in output for marker in markers):
            reasons.append("final output lost one or more tool-result markers")
        if not any(bool(stat.get("context_truncated")) for stat in stats):
            reasons.append("model context was not truncated under the configured soft budget")
        if reasons:
            return _result(name, started, context.config, traces, status="fail", failure_reason=_failure("; ".join(reasons), traces))
        return _result(name, started, context.config, traces)
    except Exception as exc:
        return _result(name, started, context.config, traces, status="fail", failure_reason=_failure(f"{type(exc).__name__}: {exc}", traces))


def _trace_context_stats(trace: AgentRunTrace) -> list[dict[str, Any]]:
    keys = {"context_chars_before", "context_chars_after", "context_truncated", "context_budget_overflow"}
    return [{key: value for key, value in call.metadata.items() if key in keys} for call in trace.llm_calls]


async def _run_browser(context: LiveEvalContext) -> LiveEvalResult:
    name = "browser_live"
    started = time.perf_counter()
    traces: list[AgentRunTrace] = []
    try:
        prompt = (
            "Use the browser tools in read-only mode. Open https://example.com, take a snapshot, "
            "inspect the visible heading text 'Example Domain', then verify that the URL contains example.com. "
            "Do not click, type, submit, or use browser_eval. Finish only after structured verification succeeds."
        )
        output, trace = await context.agent.run_traced(
            prompt,
            [{"role": "user", "content": prompt}],
            ContextBuilder.resolve_browser_mode("Use a new managed browser for this read-only task."),
            session_key="live:browser",
            requester_sender_id="live-sender",
        )
        traces.append(trace)
        names = {call.tool_name for call in trace.tool_calls}
        reasons = []
        if trace.status != "success" or trace.task_status != "completed":
            reasons.append(f"task ended as {trace.status}/{trace.task_status}")
        for required in ("browser_open", "browser_goto", "browser_snapshot", "browser_inspect", "browser_verify"):
            if required not in names:
                reasons.append(f"model behavior did not call {required}")
        if not any(call.metadata.get("postcondition_met") for call in trace.tool_calls if call.tool_name == "browser_verify"):
            reasons.append("browser verification evidence is missing")
        if reasons:
            return _result(name, started, context.config, traces, status="fail", failure_reason=_failure("; ".join(reasons), traces))
        return _result(name, started, context.config, traces)
    except Exception as exc:
        return _result(name, started, context.config, traces, status="fail", failure_reason=_failure(f"{type(exc).__name__}: {exc}", traces))


def live_cases() -> list[LiveEvalCase]:
    return [
        LiveEvalCase("real_llm_basic", _run_basic),
        LiveEvalCase("read_file_tool", _run_read_file),
        LiveEvalCase("approval_side_effect", _run_approval_side_effect),
        LiveEvalCase("restart_recovery", _run_restart_recovery),
        LiveEvalCase("context_budget", _run_context_budget),
        LiveEvalCase("browser_live", _run_browser, browser=True),
    ]


def format_live_report(results: list[LiveEvalResult]) -> str:
    passed = sum(item.status == "pass" for item in results)
    skipped = sum(item.status == "skip" for item in results)
    lines = [f"Live E2E: {passed}/{len(results)} passed"]
    for item in results:
        lines.append(f"{item.status.upper():4} {item.name}")
        if item.failure_reason:
            lines.append(f"  {item.failure_reason}")
    if skipped:
        lines.append(f"Skipped: {skipped}")
    return "\n".join(lines)


async def run_live_suite(
    *,
    environ: dict[str, str] | None = None,
    cases: list[LiveEvalCase] | None = None,
) -> list[LiveEvalResult]:
    values = environ if environ is not None else os.environ
    selected = cases or live_cases()
    if not _enabled(LIVE_OPT_IN, values):
        return [LiveEvalResult.skipped(case.name, f"opt-in required: set {LIVE_OPT_IN}=1") for case in selected]
    key, base_url, model, provider = _api_settings(
        None if environ is None else values
    )
    if not key:
        return [LiveEvalResult.skipped(case.name, "environment/network: no API key configured") for case in selected]
    browser_reason = _browser_prerequisite() if _enabled(BROWSER_OPT_IN, values) else f"opt-in required: set {BROWSER_OPT_IN}=1"
    results: list[LiveEvalResult] = []
    for case in selected:
        if case.browser:
            if not _enabled(BROWSER_OPT_IN, values):
                results.append(LiveEvalResult.skipped(case.name, browser_reason or "browser opt-in required"))
                continue
            if browser_reason:
                results.append(LiveEvalResult.skipped(case.name, browser_reason))
                continue
        started = time.perf_counter()
        try:
            with tempfile.TemporaryDirectory(prefix=f"mybot-live-{case.name}-") as directory:
                context = await _make_context(
                    Path(directory),
                    key=key,
                    base_url=base_url,
                    model=model,
                    max_context_chars=(6000 if case.name == "context_budget" else 60_000),
                    max_tool_result_chars=(700 if case.name == "context_budget" else 8_000),
                    provider=provider,
                )
                try:
                    result = await case.run(context)
                finally:
                    await context.close()
                results.append(result)
        except Exception as exc:
            config = GatewayConfig(provider=provider, model=model, api_key=key, base_url=base_url)
            results.append(LiveEvalResult(name=case.name, status="fail", duration_ms=(time.perf_counter() - started) * 1000, provider=config.provider, model=model, failure_reason=_failure(f"{type(exc).__name__}: {exc}", [])))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run opt-in production-like live E2E evaluations")
    parser.add_argument("--json", action="store_true", help="emit report-safe JSON records")
    args = parser.parse_args(argv)
    results = asyncio.run(run_live_suite())
    if args.json:
        import json

        print(json.dumps([result.public_dict() for result in results], ensure_ascii=True, indent=2))
    else:
        print(format_live_report(results))
    return 1 if any(result.status == "fail" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
