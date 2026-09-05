# AI Handoff

## 当前目标

Phase 6.1：在已批准的高风险 Browser Action 执行前验证 fresh browser state。

## 当前状态

已完成，等待 Phase 7 的持久化与重启恢复设计。

## 已完成内容

- ToolExecutionPipeline 在 browser_click、browser_type(submit=true)、browser_press 提交键和 browser_eval 的 Approval Resume 中主动读取同 session 的 fresh browser_snapshot。
- Live precondition 只比较当前 URL、目标 ref 与 action-relevant 角色/语义，不要求整份 snapshot 相等；目标消失/变化、URL/session 变化、刷新失败或无法可靠验证时 fail closed。
- browser_type.text 继续在 Trace/debug/error 中脱敏；Runtime 内部 snapshot 不进入 Approval，Trace 标记 runtime_internal/runtime_precondition_check 与结果原因。
- 当前没有可靠 active/focused element 状态，因此 browser_press Enter/Return/Space 在 fresh snapshot 后保守拒绝。
- 非 Browser Approval 不触发 browser snapshot；Phase 6 的统一 Pipeline、冻结动作、显式 AgentTaskState、恢复与 completion gate 行为保持不变。

## 修改文件

- mybot/agent/tool_execution.py
- tests/test_tool_execution.py
- tests/test_agent_confirmation.py
- README.md
- docs/AI_HANDOFF.md

## 架构决策

- AgentLoop 只编排 Tool batch 与 pause/finish；ToolExecutionPipeline 是唯一 Agent-visible 执行边界。
- Approval authorization 允许跳过再次询问，但不跳过 lookup、validation、Policy BLOCK、TTL、runtime invariant 或轻量 browser precondition。
- Browser live precondition refresh 是 Runtime Internal Read，不经过 Approval；验证失败不执行冻结副作用 Tool。
- Snapshot 验证是 action-scoped precondition，不是整页字符串锁或完整 browser transaction。
- AgentTaskState 是小型显式 Runtime 状态，不包含 messages、Tool 实例、browser 对象或敏感 Arguments。
- Trace status 保持旧 Runtime status contract，新增 task_status 表达跨 Run 的任务状态，避免“程序无异常”等同“任务已完成”。
- Browser completion_state=verification_required 对应 waiting_verification；browser_verify 后回到 running，最终回复后才进入 completed。
- 不引入数据库、Task queue、并发执行、新 Provider、Multi-Agent 或完整 sandbox。

## 测试结果

- Baseline：189 tests，188 passed，1 skipped；Evals 43/43。
- Phase 6.1：212 tests，211 passed，0 failed，1 skipped。
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
- Browser live precondition 仍不是完整 Browser Transaction System；snapshot 读取与动作执行之间不具备原子性。

## 下一步

- Phase 7 先设计版本化、脱敏、可迁移的 Task/Approval/Clarification/Recent Browser Task 持久化格式与 restart recovery。
- 在持久化前明确 browser session ownership、跨 session 并发约束和恢复时的过期/失效策略。
- 持久化模型稳定后，再处理 context/token budget 与 Tool output compression。

## 不要重复进行的工作

- 不要恢复 AgentLoop 内独立的 normal/resume Tool 执行分支。
- 不要让 approved execution 绕过 Pipeline 的 lookup、validation、Policy BLOCK、TTL 或 Runtime invariants。
- 不要把 AgentTaskState 当作 Runtime Object Dump 或在未设计迁移/脱敏方案时直接落盘。
- 不要降低 Phase 5 的 Exec、Runtime path、Browser、Approval sender/TTL 和 redaction 约束。
