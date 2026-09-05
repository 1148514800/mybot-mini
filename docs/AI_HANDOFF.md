# AI Handoff

## 当前目标

Runtime Consolidation：Checkpoint storage and task lifecycle boundaries。

## 当前状态

已完成，等待后续上下文摘要或 artifact reference 评估。

## 已完成内容

- 新增 `ActiveTaskCheckpointStore`，在 `workspace/checkpoints/active_tasks.sqlite3` 中以 SQLite transaction、JSON-compatible payload 和 `schema_version=1` 持久化 waiting AgentTaskState、PendingApproval、PendingClarification 与 RecentBrowserTask；不使用 pickle。
- Gateway 默认启用 checkpoint，可通过 `checkpoint.enabled=false` 保持原有纯内存行为；Recent Browser Task TTL 默认 86400 秒。
- 启动恢复只重建内存等待状态，不调用 LLM 或执行 Tool。恢复 Approval 仍检查 TTL、sender、task、schema、Policy 与 Phase 6.1 fresh browser precondition。
- Approval 在恢复执行前先消费并删除 active row；崩溃后不会自动重放。重启前批次中未独立批准的其余 Tool Call 会跳过并重新评估。
- password/token/cookie/authorization/secret/API key、`browser_type.text` 与相关消息内容写入前脱敏；丢失安全恢复所需参数的 Approval 标记 non-resumable。
- Persisted browser state 只作历史上下文：Clarification/Verification/Recent Task 恢复后清空 live snapshot/initialized 标记；Browser Approval 仅保留最小 URL/目标语义用于 fresh-state 比较。
- corrupt row、identity mismatch、过期记录与 unsupported schema 均 fail closed；completed/failed/max_steps/cancelled 清除 active checkpoint。
- `checkpoints/` 纳入 Runtime-managed path，普通 `write_file` 无法修改。
- Durable Approval/continuation consume 在副作用或恢复前必须成功删除 active row；删除失败 fail closed。Clarification 继续校验 requester sender，RecentTaskManager 内存 lookup 同样执行 timezone-aware TTL 并清理过期 checkpoint row。
- ContextBuilder 集中管理模型输入字符预算：系统/指令和当前用户输入优先保留，历史、Memory 与 Tool Result 确定性裁剪；Tool Result 使用前后片段与 truncation marker。原始 ToolResult、Trace 与浏览器 live precondition 不受压缩影响。
- Tool call 与对应 tool response 作为完整原子 unit 一起保留或删除；孤立 tool response 不进入模型输入。`build_messages()` 保留完整 runtime chain，仅在 LLM request boundary 生成压缩副本。`max_context_chars` 是 soft target，required context 超出时记录 `context_budget_overflow`。
- Compaction 保持 runtime message 的原始 relative order，不把 current user 移到末尾；task anchor 使用明确的原始用户输入匹配，避免被 Runtime synthetic user message 替换。统一 message size estimator 计入 content、tool call payload、IDs 和 arguments；duplicate/missing/invalid tool response unit fail closed。
- Checkpoint SQLite implementation moved to `mybot/storage/checkpoints/store.py`, with compatibility export at `mybot/storage/checkpoint.py`; public models, serialization adapters and sanitizer exports have dedicated module locations. `TaskRuntimeManager` now owns task lifecycle, checkpoint restore/sync and durable consume coordination, leaving AgentLoop as orchestration boundary.

## 修改文件

- `mybot/storage/checkpoint.py`
- `mybot/agent/checkpoint_recovery.py`
- `mybot/agent/loop.py`
- `mybot/agent/task_state.py`
- `mybot/agent/browser_reliability.py`
- `mybot/agent/tool_execution.py`
- `mybot/guardrails/models.py`
- `mybot/guardrails/approvals.py`
- `mybot/guardrails/clarifications.py`
- `mybot/guardrails/paths.py`
- `mybot/core/config.py`
- `mybot/core/app.py`
- `mybot/evals/fakes.py`
- `config/config.example.json`
- `tests/test_checkpoints.py`
- `tests/test_file_tools.py`
- `tests/test_guardrail_policy.py`
- `tests/test_llm_client.py`
- `README.md`
- `docs/AI_HANDOFF.md`

## 架构决策

- SQLite 与 schema/sanitization/expiry 逻辑位于 `mybot/storage/`；AgentLoop 只在 pause/finish 边界同步状态并调用 typed recovery adapter。
- `active_tasks` 每个 session 保留一个 waiting checkpoint；`recent_browser_tasks` 独立保存最近浏览器任务，使 active terminal cleanup 不影响纠正续接。
- 每条记录同时校验 DB schema、payload schema、kind、session、task 和 resumable identity；损坏或未知版本不做猜测性迁移。
- 重启恢复采用安全的 at-most-once 语义：副作用执行前删除 active row。若删除后、执行前崩溃，动作会丢失但不会重复。
- Browser persisted state 不是 live capability 或 page authority；所有恢复动作仍经过统一 ToolExecutionPipeline。

## 测试结果

- Runtime Consolidation focused regression tests：通过（Windows SQLite temporary-file lock remains an environment issue）；离线 Evals：43/43 passed。
- 全量单元测试：236 tests，2 failures，1 error，1 skipped；失败为既有 Windows 沙箱 Playwright daemon/Exec 权限及 SQLite 临时文件锁环境问题。

- Phase 7.1 focused checkpoint/clarification tests：21 tests，业务断言通过；Windows 临时目录清理仍有 1 个 SQLite 文件锁环境错误。
- 全量单元测试：225 tests，224 passed，0 failed，1 skipped。
- 离线 Evals：43/43 passed，100%。
- `git diff --check` 通过。
- 跳过项为需要 `MYBOT_RUN_BROWSER_INTEGRATION=1` 的本地 Chrome 集成测试。

## 已知问题

- SQLite 文件未加密；当前依靠数据最小化、脱敏、文件权限与 Runtime path 保护，仍不替代磁盘加密/OS ACL。
- at-most-once 安全语义可能在消费 checkpoint 后崩溃时丢失一次已确认动作，需要用户重新发起；durable delete 失败现在会明确拒绝执行。
- Browser live snapshot 与副作用动作之间仍非原子 Transaction，页面可在两者之间变化。
- Unsupported schema 当前 fail closed，不提供自动迁移。
- Cross-session concurrency、Browser session ownership、Tool output artifact reference 尚未实现。
- 真实模型、真实站点和用户交互的 E2E Eval 仍缺失。
- 完整单元测试在当前 Windows 沙箱中另有既有环境失败：Playwright daemon 写入权限、Exec 工作目录权限；不影响本阶段相关测试。
- ToolPolicy 是应用层 Runtime Safety Layer，不是 OS sandbox。

## 下一步

- 后续可单独评估 Context 摘要或 artifact reference；不要引入 Vector DB/RAG 或进一步扩大 AgentLoop 重构。
- 再后续单独处理 cross-session concurrency、Browser session ownership 与多 Agent/session orchestration；不要在 Phase 8 顺带重构。

## 不要重复进行的工作

- 不要把 SQLite、JSON migration 或脱敏逻辑移入 AgentLoop。
- 不要在启动恢复时调用模型、执行 frozen Tool 或信任 persisted browser state。
- 不要让 resumed Approval 绕过 lookup、schema、Policy、TTL、sender/task 或 live browser precondition。
- 不要为 exactly-once 假设自动重放副作用；当前刻意选择 fail-closed at-most-once。
- 不要降低 Exec、Runtime path、Browser、Approval sender/TTL 和 redaction 约束。
