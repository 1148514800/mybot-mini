from __future__ import annotations

import re
from pathlib import Path


def grade(case, reply, workspace: Path, trace, plan, skills_enabled):
    """Deterministic rubric, grounded in actual tool results and artifacts."""
    rules = case["expect"]
    checks = {"no_runtime_error": trace.error is None,
              "finished": trace.finish_reason == "finished",
              "plan_complete": not plan.steps or all(s.status == "completed" for s in plan.steps)}
    tools = [e for e in trace.events if e["event"] == "tool"]
    allowed_failures = rules.get("allowed_failures", [])
    checks["tool_results"] = all(e["success"] or e["name"] in allowed_failures for e in tools)
    for name in rules.get("tools", []):
        checks["tool:" + name] = any(e["name"] == name and e["success"] for e in tools)
    for path in rules.get("read_paths", []):
        checks["read:" + path] = any(e["name"] == "read_file" and e["success"] and e.get("fixture_path") == path for e in tools)
    for name in rules.get("failed_tools", []):
        checks["failure:" + name] = any(e["name"] == name and not e["success"] for e in tools)
    for word in rules.get("contains", []):
        checks["fact:" + word] = word.casefold() in reply.casefold()
    for word in rules.get("forbidden", []):
        checks["not:" + word] = word.casefold() not in reply.casefold()
    if rules.get("direct"):
        checks["direct"] = not plan.steps
    if rules.get("planned"):
        checks["planned"] = bool(plan.steps)
    expected_skill = case.get("expected_skill")
    checks["skill_selection"] = (expected_skill in trace.skills if expected_skill and skills_enabled else not trace.skills)
    for path, expected in rules.get("files", {}).items():
        target = (workspace / path).resolve()
        valid = target.is_relative_to(workspace.resolve()) and target.is_file() and target.stat().st_size <= 100000
        text = target.read_text(encoding="utf-8") if valid else ""
        checks["artifact:" + path] = valid and (text == expected["exact"] if "exact" in expected else all(s in text for s in expected["contains"]))
    if "defects" in rules:
        found = set(re.findall(r"DEFECT:\s*([A-Z_]+)", reply))
        expected = set(rules["defects"])
        checks["defect_hits"] = expected <= found
        checks["no_false_defects"] = found <= expected
        review = {"true_positives": len(found & expected), "false_positives": len(found - expected), "missed": len(expected - found)}
    else:
        review = None
    return {"task_success": all(checks.values()), "checks": checks,
            "grading_reasons": [key for key, value in checks.items() if not value],
            "review_findings": review, "manual_review_required": rules.get("manual_review", False)}


def summarize(results):
    groups = {}
    for enabled in (False, True):
        items = [r for r in results if r["skills_enabled"] == enabled]
        groups["skills_on" if enabled else "skills_off"] = {
            "cases": len(items), "successes": sum(r["task_success"] for r in items),
            "success_rate": sum(r["task_success"] for r in items) / len(items) if items else None,
            **{key: sum(r[key] for r in items) for key in ("tool_calls", "tool_failures", "llm_requests", "duration_seconds")},
            **{key: sum(r[key] for r in items) if items and all(r[key] is not None for r in items) else None for key in ("input_tokens", "output_tokens")},
            "skill_selections": sum(bool(r["skill_selected"]) for r in items)}
    return groups
