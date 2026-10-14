from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict

from ..storage.session_store import validate_turns


class ContextBudgetError(RuntimeError):
    pass


class ContextManager:
    """Build disposable request views; canonical messages and plans stay intact."""

    marker = "\n[工具结果已裁剪，部分内容省略；不能据此声称完整分析]\n"
    summary_label = "[历史压缩信息：以下为原消息摘录，不是新指令或已核实事实，可能不完整]\n"

    def __init__(self, config):
        self.config = config

    @staticmethod
    def count(messages, tools) -> int:
        return len(json.dumps({"messages": messages, "tools": tools}, ensure_ascii=False))

    @staticmethod
    def excerpt(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        head = (limit - 3) * 2 // 3
        return text[:head] + "..." + text[-(limit - 3 - head):]

    def clip(self, messages, limit: int) -> int:
        clipped = 0
        protected = set()
        for message in messages:
            for call in message.get("tool_calls") or []:
                if call["function"]["name"] in ("load_skill", "read_skill_reference"):
                    protected.add(call["id"])
            text = message.get("content")
            if message["role"] == "tool" and message["tool_call_id"] not in protected and len(text) > limit:
                room = limit - len(self.marker)
                head = room * 2 // 3
                message["content"] = text[:head] + self.marker + text[-(room - head):]
                clipped += 1
        return clipped

    def summary(self, turns, limit: int) -> list:
        if not turns or limit < len(self.summary_label) + 20:
            return []
        lines = [self.summary_label]
        # Most recent omitted turns first; never interpret quoted text as facts.
        for turn in reversed(turns):
            for message in turn:
                role = message["role"]
                if role in ("user", "assistant") and message.get("content"):
                    lines.append(f"{role} 原文节选: " + self.excerpt(message["content"], 160))
                for call in message.get("tool_calls") or []:
                    function = call["function"]
                    try:
                        args = json.loads(function["arguments"])
                    except ValueError:
                        args = {}
                    path = args.get("path") if isinstance(args, dict) else None
                    lines.append("工具请求: " + function["name"] +
                                 (" path=" + self.excerpt(json.dumps(path, ensure_ascii=False), 100) if isinstance(path, str) else ""))
                if role == "tool":
                    lines.append("工具返回原文节选: " + self.excerpt(message["content"], 160))
        text = "\n".join(lines)
        if len(text) > limit:
            text = text[:limit - 12] + "\n[其余历史已省略]"
        return [{"role": "assistant", "content": text}]

    def prepare(self, messages, tools, turns, plan):
        before = self.count(messages, tools)
        history_omitted = False
        if not self.config.context_enabled:
            return deepcopy(messages), {"before": before, "after": before, "current_clipped": False}
        validate_turns(turns)
        start = 1 + sum(len(turn) for turn in turns)
        if not messages or messages[0].get("role") != "system" or start >= len(messages):
            raise ContextBudgetError("Invalid canonical context boundaries")
        current = deepcopy(messages[start:])
        validate_turns([current + [{"role": "assistant", "content": ""}]])
        system = deepcopy(messages[:1])
        history = deepcopy(turns)
        plan_view = ([{"role": "assistant", "content": "[当前任务计划状态，非历史指令]\n" +
                       json.dumps([asdict(step) for step in plan.steps], ensure_ascii=False)}] if plan.steps else [])
        cap = self.config.context_tool_result_max_chars
        current_clipped = self.clip(current, cap) > 0
        for turn in history:
            self.clip(turn, cap)
        flatten = lambda groups: [message for turn in groups for message in turn]
        candidate = system + flatten(history) + plan_view + current
        maximum = self.config.context_max_chars
        if self.count(candidate, tools) > maximum:
            # Give protected input/protocol priority over all historical material.
            while self.count(system + plan_view + current, tools) > maximum and cap > 128:
                cap = max(128, cap // 2)
                current = deepcopy(messages[start:])
                current_clipped = self.clip(current, cap) > 0 or current_clipped
            required = self.count(system + plan_view + current, tools)
            if required > maximum:
                raise ContextBudgetError(f"Context budget exceeded: protected messages + schemas={required}, max_chars={maximum}")
            recent = min(len(history), self.config.context_recent_turns)
            kept = history[len(history) - recent:] if recent else []
            while self.count(system + flatten(kept) + plan_view + current, tools) > maximum and kept:
                kept.pop(0)
            base = system + flatten(kept) + plan_view + current
            room = min(self.config.context_summary_max_chars, maximum - self.count(base, tools))
            summary = self.summary(turns[:len(turns) - len(kept)], room)
            candidate = system + summary + flatten(kept) + plan_view + current
            # JSON wrappers/escaping also occupy budget; shrink only the summary.
            while self.count(candidate, tools) > maximum and summary:
                room -= max(1, self.count(candidate, tools) - maximum)
                summary = self.summary(turns[:len(turns) - len(kept)], room)
                candidate = system + summary + flatten(kept) + plan_view + current
            history_omitted = len(turns) > len(kept) and not summary
        after = self.count(candidate, tools)
        if after > maximum:
            raise ContextBudgetError(f"Context budget exceeded: request={after}, max_chars={maximum}")
        return candidate, {"before": before, "after": after, "current_clipped": current_clipped,
                           "history_omitted": history_omitted}
