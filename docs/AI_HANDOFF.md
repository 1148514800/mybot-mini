# AI Handoff

## 当前目标与状态

Phase 11：大型非 Browser 文本 ToolResult 已外置为受控 Artifact；模型只收到 preview 与 artifact_id，使用受限 artifact_read 按需读取。Browser result 不外置，ToolExecutionPipeline 安全语义保持不变。

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
- `mybot/agent/model_execution.py`：集中 ContextBuilder message preparation、OpenAI-compatible request、timeout/rate-limit retry、LLM trace 和 usage/result 提取。
- `mybot/agent/tool_calls.py`：提供无状态的 tool call signature、serialize、deserialize 纯函数。
- `mybot/agent/loop.py`：直接使用 `TaskRuntimeManager`，移除 checkpoint/approval delegation wrappers 和 tool-call codec；ReAct 模型请求改由 `ModelExecutor` 执行。
- `tests/test_model_execution.py`、`tests/test_tool_calls.py`：覆盖模型请求、trace/timeout、无 active trace 和 codec round-trip。
- `mybot/evals/live.py`：restart 重建上下文完整继承原 `GatewayConfig` 的 provider/model/key/base URL、context/react/tool/result/request 限制；Browser smoke 明确要求五个只读工具顺序并验证 `browser_verify.success` 与 `postcondition_met=true`，拒绝副作用 Browser Tool。
- `tests/test_live_evals.py`：新增 custom provider/model restart 配置一致性 regression test。
- `mybot/core/concurrency.py`：新增按 session 串行、跨 session 并发且有 `1..32` 上限的 coordinator。
- `mybot/core/config.py`、`config/config.example.json`：新增 `max_concurrent_sessions`，默认 4。
- `mybot/agent/loop.py`：入站消息创建受 coordinator 管理的 inflight task；shutdown cancel/await 全部任务。
- `mybot/tracing/tracer.py`：`current_run/current_step` 改为 `ContextVar`，并发 run 独立记录。
- `mybot/tools/browser/session.py`、`mybot/tools/registry.py`：新增进程级 Browser exclusive lease；冲突 fail closed，close 成功释放。
- `mybot/agent/tool_execution.py`：把 trusted `session_key/task_id` 传到 registry boundary。
- `tests/test_concurrency.py`：覆盖 session overlap/serialization、Tracer isolation、Browser ownership/release。
- `README.md`：记录调度、shutdown 与 Browser lease 语义。
- `AGENTS.md`：记录 GitHub 仓库名称与远端地址。
- `mybot/tools/browser/session.py`、`mybot/tools/registry.py`：无 owner 的 Browser 操作 fail closed；空 trusted session identity fail closed；只有 `browser_open`/`browser_attach` 可在无 owner 时尝试 acquire。
- `mybot/tracing/tracer.py`：run owner 与 current run 使用 task-local ContextVar；仅同步兼容路径允许无 event-loop 的历史 post-run 检查，不向其他 asyncio task 暴露 last run。
- `tests/test_concurrency.py`、`tests/test_tool_execution.py`：覆盖 no-owner、missing identity、restart lease reset 与 post-run isolation。
- `mybot/storage/artifacts/`：新增 text-only、session-bound ArtifactRecord/ArtifactStore，原子写入、脱敏、sha256、存储上限和 bounded offset/query 读取。
- `mybot/tools/artifact.py`、`mybot/tools/registry.py`、`mybot/tools/base.py`：新增受 trusted Runtime identity 约束的 `artifact_read`，模型 schema 不暴露 owner。
- `mybot/agent/artifact_results.py`、`mybot/agent/loop.py`：大型非 Browser model-facing result 统一 externalize；记录 run artifact metadata，Browser 与 runtime result 保持完整。
- `mybot/core/config.py`、`config/config.example.json`、`mybot/core/app.py`：新增 Artifact 配置并组装共享 store。
- `mybot/guardrails/paths.py`、`mybot/tools/file_tools.py`、`mybot/tools/exec.py`：保护 Runtime-managed `artifacts/` 路径。
- `tests/test_artifacts.py`：覆盖外置、脱敏、bounded/query、缺失 identity、session 隔离和并发写入。
- `README.md`：记录 Artifact 配置、读取边界和 Runtime 路径保护。

## 架构决策与行为约束

- 依赖方向：RuntimeManager → store / serialization；store → models / serialization；serialization → sanitizer / guardrail models；sanitizer → tracing。models 无项目内部依赖。
- RecentBrowserTask 仍属于现有 browser_reliability 模块；serializer 在恢复函数内延迟导入该数据类型，避免 agent 包初始化带来的循环导入，不依赖 agent/checkpoint_recovery 的实现。
- SQLite `active_tasks` 每 session 一个 waiting checkpoint；`recent_browser_tasks` 独立存储并按 timezone-aware TTL 清理。DB/payload schema、kind、session、task、sender、expiry、resumable identity 继续 fail closed。
- 重启只恢复等待状态，不调用 LLM 或 Tool。副作用前必须成功消费 active row，保证 at-most-once；未单独批准的旧批次调用不自动重放。
- secret 写入前脱敏；恢复所需敏感参数被清除时 Approval non-resumable。Persisted browser state 仅历史上下文，Approval 仍检查 fresh live precondition、Policy、TTL 和 sender/task。
- ContextBuilder 的预算及 tool call/response 原子裁剪保持不变；runtime chain 完整，仅 LLM request boundary 压缩，required context 超预算记录 overflow。
- AgentLoop 从 1827 行降至 1691 行；依赖方向为 AgentLoop → ModelExecutor / tool_calls，ModelExecutor → ContextBuilder / client / tracer，纯 codec 不依赖 Runtime、Tool、Approval 或 Browser。Browser 核心行为未改动，ToolExecutionPipeline 未拆分。

## 测试结果

本阶段在 Windows 沙箱工作区验证：

- `.venv\Scripts\python.exe -m unittest discover -s tests -v`：262 tests；功能性回归通过。剩余 2 failures 与 1 error 均为 Windows 环境限制（Playwright daemon/Exec 工作目录 EPERM，以及 SQLite 临时文件锁 WinError 32）。
- 定向 Concurrency、Tracer、ModelExecution、ToolExecution、AgentLoop、Checkpoint 测试：30/30 passed。
- 新增 Live harness 单测及 checkpoint/approval 相关回归通过；剩余失败是既有环境限制：Playwright daemon 写入 `EPERM`、Exec 工作目录权限失败、SQLite 临时文件清理时文件锁 `WinError 32`。
- 跳过项为需要 `MYBOT_RUN_BROWSER_INTEGRATION=1` 的本地 Chrome 集成测试。
- `.venv\Scripts\python.exe -m mybot.evals.runner`：44/44 passed，100%；新增 Artifact Results case。
- `git diff --check`：通过。
- `uv run python -m mybot.evals.live`（无 opt-in）：6/6 明确 SKIP，退出码 0。
- `MYBOT_RUN_LIVE_E2E=1 uv run python -m mybot.evals.live`（luchikey / `gpt-5.6-sol`，Browser opt-in 未启用）：5/6 passed；`real_llm_basic`、`read_file_tool`、`approval_side_effect`、`restart_recovery`、`context_budget` 真实执行通过；`browser_live` 因未设置 `MYBOT_RUN_BROWSER_LIVE_E2E=1` SKIP。
- 本轮重构后 Live E2E 结果无 behavior regression：同一命令再次得到 5/6 passed，Browser Live 明确 SKIP。
- Phase 9.5 harness 修复后：一次真实运行 `restart_recovery` PASS；重复运行受 provider 间歇返回 `unknown provider for model gpt-5.6-sol` 影响，最终一次报告为 4/6。Browser Live 仍未通过：一次运行因 Playwright/Chrome 初始化 `EPERM` 失败，另一轮因同一 provider 错误未进入工具链；独立 Browser trace 中工具顺序为 `browser_open, browser_open, browser_goto, browser_snapshot, browser_inspect, browser_verify`，`browser_verify.postcondition_met=false`，未判定为 Runtime correctness bug。

## 已知问题

- SQLite 未加密；数据最小化、脱敏、文件权限和 Runtime path 保护不能替代磁盘加密。
- durable consume 成功后、执行前崩溃可能丢失一次动作，需要用户重新发起；不自动重放。
- Browser live snapshot 与副作用之间仍非原子事务；unsupported schema 不提供迁移。
- Browser ownership 不持久化；进程重启后 lease 为 none，恢复动作必须先重新建立 live Browser 状态。Browser Live 尚未在本次运行启用。
- Artifact 文件独立于 checkpoint 持久化；同 session 重启后可通过 `artifact_read` 读取，artifact ownership 不跨 session 转移。
- Artifact Store 当前没有 TTL/GC；每个文本最多保存 1,000,000 字符，长期运行仍需运维清理旧 artifacts。
- `SessionExecutionCoordinator._locks` 不回收；本阶段仅记录为 remaining risk。
- 无 owner 或缺失 trusted session identity 的 Browser 调用不会进入真实 Tool；重启恢复不会从 persisted browser state 恢复 ownership。

## 下一步

- 在具备 Browser 条件且 provider 稳定的隔离环境运行 `MYBOT_RUN_LIVE_E2E=1 MYBOT_RUN_BROWSER_LIVE_E2E=1 uv run python -m mybot.evals.live`；本轮未改变 Browser 核心。
- Phase 11 已实现；后续可在稳定 provider/Browser 条件下运行完整 live suite。

## 不要重复进行的工作

- 不要继续为达到行数目标拆分 AgentLoop；不要把 SQLite、payload 转换、脱敏或 Browser 核心移回 AgentLoop / Store。
- 不要通过 Store 私有方法暴露 sanitizer，或让 models / sanitizer 反向依赖 Store。
- 不要在启动恢复时执行 Tool、信任 persisted browser state 或自动重放副作用。
- 不要降低 sender/TTL/task、Policy、live precondition、Context Budget、Runtime path 与 secret redaction 约束。
- 不要把 Browser snapshot/result、Artifact 内容或 filesystem path 写入模型以外的 checkpoint schema；不要让模型参数提供 Artifact owner。
