# AI Handoff

## 当前目标与状态

Agent 功能裁剪完成：删除 Evals、Guardrails（Tool Policy / Approval / Clarification）、
Messaging（消息总线 + 飞书通道）和长期记忆四个子系统，只保留 Agent 基本功能
（CLI 对话、ReAct 循环、Tool 执行、Browser、MCP、Skills、Tracing、Checkpoint）。

当前入口是纯 CLI 交互循环；不再有消息总线抽象，也不再有任何审批 / 澄清暂停状态。

## 已完成内容与修改文件

**删除的模块**

- `mybot/evals/`、根目录 `evals/`：确定性 Eval runner / FakeLLM / live harness 与全部 EvalCase JSON。
- `mybot/guardrails/`（policy、approvals、clarifications、models、paths）、`mybot/tools/runtime.py`（RequestUserInputTool）。
- `mybot/messaging/`（bus、channels、Feishu 通道）。
- `mybot/storage/memory/`、`mybot/tools/memory.py`。
- 对应测试：`test_approval_manager`、`test_clarification_manager`、`test_guardrail_policy`、
  `test_agent_confirmation`、`test_agent_clarification`、`test_mcp_policy`、`test_memory`、
  `test_eval_*`、`test_live_evals`。

**改造的核心模块**

- `mybot/agent/loop.py`：由消息驱动改为直接 CLI 读循环。`run()` 用 `asyncio.to_thread(input)`
  读取 `You: `，`exit`/`quit`/EOF 退出。新增 `handle_inbound_message()` 作为唯一外部入口。
  删除全部 approval / clarification 暂停与恢复路径（`resume_pending`、`resume_clarification`、
  `_resume_approved`、approval 预览与提示等）。
- `mybot/agent/tool_execution.py`：Pipeline 现在只做 normalization → trace → 存在性 / 参数校验
  → `execution_guard` → registry 调用。`ToolExecutionStatus` 只剩 `EXECUTED` / `FAILED`。
- `mybot/agent/task_state.py`：`AgentTaskStatus` 只剩 `new / running / waiting_verification /
  completed / failed / max_steps / cancelled`。
- `mybot/agent/runtime_manager.py`：只负责 recent task 与 verification 状态。
- `mybot/agent/checkpoint_recovery.py`：只剩 `recent_task_from_checkpoint`。
- `mybot/tools/file_tools.py`：移除 Runtime-managed path 拦截。
- `mybot/core/app.py`：直接构建 `AgentLoop` 并 `await agent.run()`，打印 `Gateway started. Channel: cli`。
- `mybot/core/config.py`：移除 `FeishuConfig`、`guardrails`、`approval_ttl_seconds`、
  `max_memory_chars` 及其校验。
- `mybot/storage/checkpoints/`：serialization / sanitizer / store 移除全部 approval、
  clarification 的序列化、脱敏与 consume 逻辑；`_ACTIVE_KINDS` 只剩 `verification`。
- `mybot/mcp/config.py`、`mybot/mcp/adapter.py`：移除无人消费的 `tool_policy` 覆盖管线。
- `mybot/tracing/models.py`、`mybot/tracing/replay.py`：移除 `awaiting_confirmation` /
  `awaiting_clarification` 状态与 policy / approval trace 字段。
- `mybot/agent/tool_calls.py`：删除只为 checkpoint 持久化待审批动作而存在的
  `serialize_tool_call` / `deserialize_tool_call`。
- `mybot/tools/browser/errors.py`：删除已无生产者的 `POLICY_BLOCKED` 分类。
- `mybot/agent/context.py`：System Prompt 移除 approval / clarification / Policy Block /
  `request_user_input` 描述。
- `mybot/workspace/bootstrap.py`：不再创建 `workspace/memory/`。

**新增**

- `tests/fakes.py`：共享测试夹具（`FakeCase`、`FakeCompletions`、`FakeToolRegistry`、
  `build_fake_agent`），替代被删除的 `mybot.evals.fakes` / `models`。

**配置与依赖**

- `config/config.example.json`：删除 `feishu`、`guardrails`、`llm.max_memory_chars` 与 MCP `tool_policy`。
- `pyproject.toml` / `uv.lock`：删除 `lark-oapi`（连带移除 7 个仅飞书使用的传递依赖）。
- `.gitignore`：删除 `workspace/memory/`。
- `README.md`：重写功能概览、项目结构、Runtime 架构、Tracing、MCP 章节，删除飞书、
  Evals、Guardrails、Clarification、记忆相关内容。

## 测试结果

- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：176 tests，1 failure + 1 skip。
- 唯一失败 `tests/test_exec.py::test_commands_run_with_workspace_as_cwd` 是**既有环境问题**
  （测试依赖 `pwd`，Windows `cmd` 无此内建命令），不是本次裁剪引入的回归；skip 为既有的
  Playwright 集成用例。
- `python -m compileall -q mybot tests`：通过。

## 已知问题

- 删除 Guardrails 后不再有任何工具级审批 / 拦截：`exec`、`write_file` 等可被模型直接调用，
  仅剩 `exec` 内针对 `playwright-cli` 的硬编码拒绝。这是用户明确要求的取舍。
- 删除 Memory 后，跨会话只保留 Session JSONL 对话历史，没有长期记忆层。
- 删除 Messaging 后没有并发 session 抽象，`max_concurrent_sessions` 仅保留配置字段。
- `config/config.json` 是本机真实配置（含明文 API Key），已被 `.gitignore` 忽略，不要提交。

## 下一步

- 无进行中的开发任务。如需恢复审批 / 拦截能力，应从 Git 历史取回 `mybot/guardrails/`
  与 `ToolExecutionPipeline` 的 policy 分支。

## 不要重复进行的工作

- 不要把 Evals、Guardrails、Messaging/Feishu、Memory 四个子系统重新引入；
  用户的明确目标是只保留 Agent 基本功能。
- 不要重新创建 `workspace/memory/` 目录或 `memory_write` / `memory_delete` 工具。
- 不要把消息总线抽象加回 `AgentLoop`；CLI 读循环是当前唯一入口。
- 不要提交 `config/config.json`。
