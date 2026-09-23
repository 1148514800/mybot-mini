# AI Handoff

## 当前目标与状态

第二轮裁剪完成：在上一轮（删除 Evals / Guardrails / Messaging / Memory）基础上，继续删除
用户认为"多余"的可靠性层，只保留 Agent 基本功能。

保留的能力：CLI 对话、ReAct 循环、统一 Tool 执行、Browser 工具、MCP、Skills、
Tracing、单会话上下文记忆。

## 已完成内容与修改文件

**本轮删除的模块**

- `mybot/agent/browser_reliability.py`、`task_state.py`、`runtime_manager.py`、
  `checkpoint_recovery.py`、`artifact_results.py`：浏览器预算 / 重复操作阻断 /
  `browser_verify` 完成门控 / 自动错误恢复 / 最近任务续接 / 大型结果外置。
- `mybot/storage/`（全部）：`artifacts/`、`checkpoints/`、`session/`、`checkpoint.py`。
- `mybot/core/concurrency.py`：多会话调度器（现在只有单个 CLI 会话）。
- `mybot/tools/artifact.py`。
- `workspace/skills/playwright-cli/`（10 个文件）。
- `tests/`：用户明确表示不再需要测试目录。

**本轮新增 / 迁移**

- `mybot/session.py`：由 `mybot/storage/session/manager.py` 迁移而来，包含
  `Session` 与 `SessionManager`。这是用户要求的"上下文记忆"。

**本轮重写或大幅修改**

- `mybot/agent/loop.py`：删除 MessageBus、TaskRuntimeManager、RecentTaskManager、
  浏览器预算与完成门控。`run()` 是纯 CLI 读循环；`handle_inbound_message()` 是唯一
  外部入口；`_react_loop_outcome` 返回 `(output, status, error)`。
- `mybot/agent/tool_execution.py`：`ToolExecutionStatus` 只剩 `EXECUTED` / `FAILED`；
  `ToolExecutionContext` 不再有 `browser_state` / `browser_budget`。
- `mybot/core/config.py`：删除 `max_concurrent_sessions`、全部 `browser_max_*`、
  `checkpoint_*`、`artifact_*`。
- `mybot/core/app.py`：构建 tools → MCP → `AgentLoop` → `await agent.run()`。
- `mybot/tracing/{models,tracer,replay}.py`：删除 `task_status` 字段。
- `mybot/tools/{registry,base,exec,__init__}.py`：移除 artifact 身份钩子与路径拦截。
- `mybot/agent/context.py`：System Prompt 删除浏览器可靠性与完成门控措辞。
- `config/config.example.json`：删除 `max_concurrent_sessions`、`browser_runtime`、
  `checkpoint`、`artifact`。
- `workspace/skills/douyin-skills/`：删除对已删 `request_user_input` 与
  `playwright-cli` Skill 的引用，改为在最终回复中向用户提问。
- `README.md`、`mybot/tools/browser/README.md`：同步裁剪后的架构。

## 验证结果

- `python -m compileall -q mybot`：通过。
- `uv run --with pyflakes python -m pyflakes mybot`：仅剩 3 条 HEAD 已存在的历史告警
  （`context.py` 的 datetime/dataclass、`tools/browser/base.py` 的 DEFAULT_SESSION）。
- 导入与构造检查：`GatewayConfig`、`build_default_tool_registry`（16 个工具）、
  `AgentLoop` 均正常。
- 端到端烟测（假 LLM + 真实 `exec` 工具）：`handle_inbound_message` 正常完成，
  Trace 写入正确，会话写入 `workspace/sessions/cli_direct.jsonl`。
- 测试套件已按用户要求删除，不再运行。

## 已知问题

- 删除 Guardrails 后没有工具级审批 / 拦截；`exec`、`write_file` 可被模型直接调用。
- 删除可靠性层后，浏览器失败不再自动恢复，重试完全由模型判断；`browser_verify` 仍在，
  但完成与否不再由 Runtime 强制门控。
- 没有测试目录，回归只能靠手工烟测。
- `config/config.json` 是本机真实配置（含明文 API Key），已被 `.gitignore` 忽略。

## 下一步

- 无进行中的开发任务。

## 不要重复进行的工作

- 不要把 Evals、Guardrails、Messaging/Feishu、长期记忆重新引入。
- 不要把 `storage/`（artifact 外置 / SQLite checkpoint）、`core/concurrency.py`、
  `browser_reliability.py` 或任务状态机加回来。
- 不要把 `tests/` 目录恢复；用户明确说明不需要。
- 不要把消息总线抽象加回 `AgentLoop`。
- 不要提交 `config/config.json`。
