# AI Handoff

## 当前目标与状态

Phase 9：Production-like Live E2E harness（真实模型/Runtime 链路，默认 skip）。Harness 已完成并使用 luchikey 配置取得非浏览器 Live PASS。

## 已完成内容与修改文件

- `mybot/storage/checkpoints/models.py`：真实定义 schema version、默认 Recent Task TTL 和 RecoveredActiveCheckpoint，不依赖 store。
- `mybot/storage/checkpoints/sanitizer.py`：真实实现 tool arguments、messages、tool calls、browser state、敏感文本、approval snapshot 与 policy metadata 脱敏；不依赖 Store。
- `mybot/storage/checkpoints/serialization.py`：Approval / Clarification / RecentBrowserTask 的 payload 编码与恢复转换，以及 recent recovery payload 归一化。
- `mybot/storage/checkpoints/store.py`：837 → 475 行；只保留 SQLite/schema、事务、CRUD、TTL、行身份校验、durable consume、JSON I/O 与错误处理。
- `mybot/storage/checkpoints/__init__.py` 与 `mybot/storage/checkpoint.py`：保留兼容 Store、常量和恢复行模型导出。
- `mybot/agent/checkpoint_recovery.py`：仅兼容导出；`mybot/agent/runtime_manager.py` 直接使用 storage serializer。
- `tests/test_checkpoint_modules.py`：新增冷启动导入兼容、脱敏不修改 live 输入、恢复 sender/task/TTL 绑定测试。
- `mybot/evals/live.py`：六个显式 opt-in case（basic、read_file、approval、restart、context budget、browser read-only），每 case 使用临时 workspace，结果脱敏并记录 task/run/provider/model、Tool/LLM 计数、Trace context stats 和失败分类。
- `tests/test_live_evals.py`：覆盖默认 opt-in、无 key、Browser 条件和脱敏报告。
- `mybot/agent/loop.py`：`resume_pending()` 在消费 durable checkpoint 前先校验原 sender，错误 sender 不会删除待确认记录。
- `mybot/evals/live.py`：CLI 未传入隔离 env 时正确回退到 `config/config.json`；Trace 中的认证/网络错误归类为 `environment/network` 并保留脱敏短原因。

## 架构决策与行为约束

- 依赖方向：RuntimeManager → store / serialization；store → models / serialization；serialization → sanitizer / guardrail models；sanitizer → tracing。models 无项目内部依赖。
- RecentBrowserTask 仍属于现有 browser_reliability 模块；serializer 在恢复函数内延迟导入该数据类型，避免 agent 包初始化带来的循环导入，不依赖 agent/checkpoint_recovery 的实现。
- SQLite `active_tasks` 每 session 一个 waiting checkpoint；`recent_browser_tasks` 独立存储并按 timezone-aware TTL 清理。DB/payload schema、kind、session、task、sender、expiry、resumable identity 继续 fail closed。
- 重启只恢复等待状态，不调用 LLM 或 Tool。副作用前必须成功消费 active row，保证 at-most-once；未单独批准的旧批次调用不自动重放。
- secret 写入前脱敏；恢复所需敏感参数被清除时 Approval non-resumable。Persisted browser state 仅历史上下文，Approval 仍检查 fresh live precondition、Policy、TTL 和 sender/task。
- ContextBuilder 的预算及 tool call/response 原子裁剪保持不变；runtime chain 完整，仅 LLM request boundary 压缩，required context 超预算记录 overflow。

## 测试结果

本阶段在 Windows 沙箱工作区验证：

- `uv run python -m unittest discover -s tests -v`：243 tests，238 passed，1 skipped，2 failures，1 error。
- 新增 Live harness 单测及 checkpoint/approval 相关回归通过；剩余失败是既有环境限制：Playwright daemon 写入 `EPERM`、Exec 工作目录权限失败、SQLite 临时文件清理时文件锁 `WinError 32`。
- 跳过项为需要 `MYBOT_RUN_BROWSER_INTEGRATION=1` 的本地 Chrome 集成测试。
- `uv run python -m mybot.evals.runner`：43/43 passed，100%。
- `git diff --check`：通过。
- `uv run python -m mybot.evals.live`（无 opt-in）：6/6 明确 SKIP，退出码 0。
- `MYBOT_RUN_LIVE_E2E=1 uv run python -m mybot.evals.live`（luchikey / `gpt-5.6-sol`，Browser opt-in 未启用）：5/6 passed；`real_llm_basic`、`read_file_tool`、`approval_side_effect`、`restart_recovery`、`context_budget` 真实执行通过；`browser_live` 因未设置 `MYBOT_RUN_BROWSER_LIVE_E2E=1` SKIP。

## 已知问题

- SQLite 未加密；数据最小化、脱敏、文件权限和 Runtime path 保护不能替代磁盘加密。
- durable consume 成功后、执行前崩溃可能丢失一次动作，需要用户重新发起；不自动重放。
- Browser live snapshot 与副作用之间仍非原子事务；unsupported schema 不提供迁移。
- Cross-session concurrency、Browser ownership、artifact reference 尚未实现；Browser Live 尚未在本次运行启用。

## 下一步

- 在具备真实 API key 的隔离环境运行 `MYBOT_RUN_LIVE_E2E=1 uv run python -m mybot.evals.live`；浏览器场景另加 `MYBOT_RUN_BROWSER_LIVE_E2E=1` 与 `playwright-cli`。
- 如评估 Context 摘要或 artifact reference，应作为独立任务，保持当前 checkpoint 安全与兼容契约。

## 不要重复进行的工作

- 不要再拆 AgentLoop，或把 SQLite、payload 转换、脱敏移回 AgentLoop / Store。
- 不要通过 Store 私有方法暴露 sanitizer，或让 models / sanitizer 反向依赖 Store。
- 不要在启动恢复时执行 Tool、信任 persisted browser state 或自动重放副作用。
- 不要降低 sender/TTL/task、Policy、live precondition、Context Budget、Runtime path 与 secret redaction 约束。
