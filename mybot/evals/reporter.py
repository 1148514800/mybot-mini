from __future__ import annotations

from collections import defaultdict

from .models import EvalCase, EvalResult


def format_eval_report(
    results: list[EvalResult],
    cases: list[EvalCase],
) -> str:
    case_by_id = {case.id: case for case in cases}
    passed = sum(result.passed for result in results)
    total = len(results)
    success_rate = (passed / total * 100) if total else 0.0

    category_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for result in results:
        case = case_by_id.get(result.case_id)
        category = (
            str(case.metadata.get("category", "uncategorized"))
            if case
            else "uncategorized"
        )
        category_counts[category][1] += 1
        category_counts[category][0] += int(result.passed)

    lines = [
        "=" * 40,
        "MYBOT AGENT EVAL",
        "=" * 40,
        "",
        f"Cases:        {total}",
        f"Passed:       {passed}",
        f"Failed:       {total - passed}",
        f"Success Rate: {success_rate:.1f}%",
        "",
    ]
    for category, counts in sorted(category_counts.items()):
        label = category.replace("_", " ").title()
        lines.append(f"{label}: {counts[0]} / {counts[1]}")

    failed_results = [result for result in results if not result.passed]
    if failed_results:
        lines.extend(["", "Failed Cases:", ""])
        for result in failed_results:
            lines.append(result.case_id)
            if result.error:
                lines.append(f"- {result.error}")
            for error in result.check_errors.values():
                lines.append(f"- {error}")
    return "\n".join(lines)
