# AI Handoff

## 当前目标

Phase 6：统一 Tool Execution Pipeline，并以显式 AgentTaskState 区分 Runtime Run 与用户任务完成状态。

## 当前状态

已完成，等待 Phase 7 的持久化与重启恢复设计。

## 已完成内容

- 新增 ToolExecutionPipeline，统一 normal ReAct、Approval Resume 和同批剩余 Tool Call 的 lookup、参数归一化/schema 校验、Policy、Approval、执行、ToolResult、Trace 与 browser state 更新。
- Approval Resume 只执行 PendingApproval 冻结的 Tool 和 Arguments；仍重新检查 tool、参数、TTL、sender、task、BLOCK/invariant 以及可验证的 browser snapshot/URL precondition。
- 未知 Tool、非法 JSON、缺少字段和参数类型错误统一返回结构化 ToolResult，不再因执行入口不同而抛出不同错误。
- Browser task preflight、Skill/browser 初始化去重、结果状态更新与有限 snapshot recovery 已移入统一执行边界；内部 recovery helper 不冒充 Agent-visible Tool。
- 新增可序列化 AgentTaskState，明确 new、running、waiting_approval、waiting_clarification、waiting_verification、completed、failed、max_steps、cancelled。
- AgentRunTrace 新增向后兼容的 task_id/task_status；status 继续表示 Runtime Run 状态，旧 Trace 缺少新字段仍能加载和 Replay。
- TaskState 不保存 Tool Arguments、浏览器输入或 secrets；所有状态仍只在进程内，未实现持久化或 Restart Recovery。
- AgentLoop 从 2037 行降至 1749 行，移除了重复的 Policy、Tool 执行、Trace 和 browser recovery 实现，保留 orchestration、LLM、pause/resume、completion gate、session/context 与最终响应职责。

## 修改文件

- mybot/agent/loop.py
- mybot/agent/task_state.py（新增）
- mybot/agent/tool_execution.py（新增）
- mybot/agent/__init__.py
- mybot/guardrails/approvals.py
- mybot/tools/registry.py
- mybot/tracing/models.py
- mybot/tracing/tracer.py
- mybot/tracing/replay.py
- tests/test_task_state.py（新增）
- tests/test_tool_execution.py（新增）
- tests/test_agent_loop.py
- tests/test_agent_confirmation.py
- tests/test_agent_clarification.py
- tests/test_agent_browser_reliability.py
- tests/test_trace_serializer.py
- tests/test_tracing_models.py
- README.md
- docs/AI_HANDOFF.md

## 架构决策

- AgentLoop 只编排 Tool batch 与 pause/finish；ToolExecutionPipeline 是唯一 Agent-visible 执行边界。
- Approval authorization 允许跳过再次询问，但不跳过 lookup、validation、Policy BLOCK、TTL、runtime invariant 或轻量 browser precondition。
- AgentTaskState 是小型显式 Runtime 状态，不包含 messages、Tool 实例、browser 对象或敏感 Arguments。
- Trace status 保持旧 Runtime status contract，新增 task_status 表达跨 Run 的任务状态，避免“程序无异常”等同“任务已完成”。
- Browser completion_state=verification_required 对应 waiting_verification；browser_verify 后回到 running，最终回复后才进入 completed。
- 不引入数据库、Task queue、并发执行、新 Provider、Multi-Agent 或完整 sandbox。

## 测试结果

- Baseline：189 tests，188 passed，1 skipped；Evals 43/43。
- Phase 6：203 tests，202 passed，0 failed，1 skipped。
- Evals：43/43 passed，100%。
- git diff --check 与修改模块 py_compile 均通过。
- 跳过项为需要 MYBOT_RUN_BROWSER_INTEGRATION=1 的本地 Chrome 集成测试。

## 已知问题

- Task state 尚未持久化。
- Runtime 重启后不能恢复任务。
- PendingApproval 尚未持久化。
- PendingClarification 尚未持久化。
- Recent browser task 尚未持久化。
- Context/token budget 尚未实现。
- Tool output compression/artifact reference 尚未实现。
- Cross-session concurrency 和 Browser session ownership 尚未解决。
- 真实模型、真实站点和用户交互的 E2E Eval 仍缺失。
- ToolPolicy 仍是应用层 Runtime Safety Layer，不是 OS sandbox。

## 下一步

- Phase 7 先设计版本化、脱敏、可迁移的 Task/Approval/Clarification/Recent Browser Task 持久化格式与 restart recovery。
- 在持久化前明确 browser session ownership、跨 session 并发约束和恢复时的过期/失效策略。
- 持久化模型稳定后，再处理 context/token budget 与 Tool output compression。

## 不要重复进行的工作

- 不要恢复 AgentLoop 内独立的 normal/resume Tool 执行分支。
- 不要让 approved execution 绕过 Pipeline 的 lookup、validation、Policy BLOCK、TTL 或 Runtime invariants。
- 不要把 AgentTaskState 当作 Runtime Object Dump 或在未设计迁移/脱敏方案时直接落盘。
- 不要降低 Phase 5 的 Exec、Runtime path、Browser、Approval sender/TTL 和 redaction 约束。
