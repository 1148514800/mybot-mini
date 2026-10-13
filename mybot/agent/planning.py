from __future__ import annotations

from dataclasses import dataclass

from ..tools import Tool, ToolResult


@dataclass
class Step:
    description: str
    status: str = "pending"
    verified: bool = False
    error: str | None = None


class Plan:
    """One task's sequential plan; completion requires real tool evidence."""

    def __init__(self):
        self.reset()

    def reset(self, task: str = "") -> None:
        self.task = task
        self.steps: list[Step] = []
        self.closed = False

    @property
    def mode(self) -> str:
        return "PLANNED" if self.steps else "DIRECT"

    @property
    def active(self) -> Step | None:
        return next((step for step in self.steps if step.status == "in_progress"), None)

    def create(self, steps: list[str]) -> str:
        if self.closed or self.steps:
            raise ValueError("A task can create only one plan; replanning is not supported")
        if not isinstance(steps, list) or not 2 <= len(steps) <= 6:
            raise ValueError("Plan must have 2 to 6 steps")
        if any(not isinstance(item, str) or not item.strip() for item in steps):
            raise ValueError("Each step must be a non-empty string")
        self.steps = [Step(item.strip()) for item in steps]
        print("[PLAN] 创建任务计划")
        for number, step in enumerate(self.steps, 1):
            print(f"[{number}/{len(self.steps)}] pending  {step.description}")
        return "Plan created. Start step 1 with update_plan before executing tools."

    def update(self, step: int, status: str) -> str:
        if self.closed or not self.steps:
            raise ValueError("No active plan for this task")
        if type(step) is not int or not 1 <= step <= len(self.steps):
            raise ValueError("step must be a valid 1-based integer")
        current = self.steps[step - 1]
        if status not in ("in_progress", "completed", "failed"):
            raise ValueError("Invalid target status")
        if status == "in_progress":
            if current.status != "pending" or any(s.status != "completed" for s in self.steps[:step - 1]):
                raise ValueError("Start only the next pending step in order")
        elif current.status != "in_progress":
            raise ValueError("Only an in_progress step can finish")
        if status == "completed" and not current.verified:
            raise ValueError("Step is unverified: no successful execution result")
        current.status = status
        if status == "failed":
            current.error = "Model reported failure; task stopped"
        print(f"[STEP {step}] {status}")
        return f"Step {step}: {status}"

    def execution_error(self) -> str | None:
        if self.steps and (self.closed or not self.active or any(s.status == "failed" for s in self.steps)):
            return "Plan cannot execute: start the next step, or stop after failure/completion"
        return None

    def observe(self, name: str, result: ToolResult) -> None:
        step = self.active
        if step is None:
            return
        print(f"[TOOL] {name}")
        if result.success:
            step.verified = True
        else:
            step.status = "failed"
            step.error = result.error or "tool execution failed"
            print(f"[STEP {self.steps.index(step) + 1}] failed")

    def close(self, reason: str = "") -> str:
        self.closed = True
        if not self.steps or all(step.status == "completed" for step in self.steps):
            return ""
        active = self.active
        if reason and active:
            active.status = "failed"
            active.error = reason
        lines = ["计划未完成；未验证步骤不能宣称成功。"]
        for number, step in enumerate(self.steps, 1):
            if step.status != "completed":
                detail = step.error or ("缺少成功执行结果或完成确认" if step.status == "in_progress" else "尚未执行")
                lines.append(f"步骤 {number}: {step.status}（{detail}）")
        return "\n".join(lines)


class PlanningTool(Tool):
    """Expose plan operations through the existing Tool/ToolRegistry protocol."""

    def __init__(self, plan: Plan, name: str):
        self.plan = plan
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return ("Create a 2-6 step plan for this task only when multiple operations are needed."
                if self.name == "create_plan" else
                "Update a plan step in order. Completion requires successful real tool execution.")

    @property
    def parameters(self) -> dict:
        properties = ({"steps": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 6}}
                      if self.name == "create_plan" else
                      {"step": {"type": "integer", "minimum": 1},
                       "status": {"type": "string", "enum": ["in_progress", "completed", "failed"]}})
        return {"type": "object", "properties": properties,
                "required": list(properties), "additionalProperties": False}

    async def execute(self, **kwargs) -> ToolResult:
        try:
            output = self.plan.create(**kwargs) if self.name == "create_plan" else self.plan.update(**kwargs)
            return ToolResult(success=True, output=output)
        except (TypeError, ValueError) as exc:
            return ToolResult(success=False, error=str(exc))
