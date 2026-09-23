# AI Handoff

## 当前目标与状态

第四轮裁剪完成：把已经删剩的功能再从"多层包"压平成"单文件模块"，代码总量继续下降，
行为保持不变。当前仓库只保留：CLI 对话、ReAct 循环、统一 Tool 执行、Browser 工具、
MCP（默认关闭）、Tracing。

## 已完成内容与修改文件

**本轮改造（扁平化）**

- `mybot/core/` → `mybot/config.py` + `mybot/app.py`。
- `mybot/tracing/`（5 个文件）→ `mybot/tracing.py`。
- `mybot/mcp/`（6 个文件）→ `mybot/mcp.py`。
- `mybot/workspace/` → `mybot/workspace.py`。
- `mybot/tools/browser/`（7 个文件 + README）→ `mybot/tools/browser.py`。
- `mybot/tools/file_tools.py` + `tools/result.py` → `mybot/tools/file.py` + `tools/base.py`。
- `mybot/agent/` 三个辅助模块合并进 `mybot/agent/loop.py`：
  删除 `model_execution.py`、`tool_calls.py`、`tool_execution.py`。
- `mybot/main.py`：ASCII 架构图与 `mcp` 包遮蔽注释同步更新。

**本轮删除的死代码**

- 配置项 `llm.max_context_chars`、`llm.max_tool_result_chars`、`mcp.servers.*.trust_annotations`
  已无任何读取方，从 `config.py`、`mcp.py`、`config/config.example.json` 一并删除。
- Trace 的 replay / serializer 公共 API。
- `GatewayConfig.__post_init__` 里冗长的逐字段校验，只保留超时与 workspace 的类型归一化。
- 浏览器 session lease / ownership 管理（单个 CLI 进程用不上）。

## 验证结果

- `python -m compileall -q mybot`：通过。
- `uv run --with pyflakes python -m pyflakes mybot`：0 条告警（原有 3 条历史告警已随文件删除消失）。
- 导入检查：`mybot`、`mybot.app`、`mybot.config`、`mybot.mcp`、`mybot.tracing`、
  `mybot.workspace`、`mybot.tools`、`mybot.agent` 全部正常；第三方 `mcp` SDK 未被
  `mybot/mcp.py` 遮蔽（解析到 site-packages）。
- Tool 注册表：仍然是 16 个工具，名称与裁剪前完全一致。
- 端到端烟测（假 LLM + 真实 `exec`）：`handle_message` 正常走完 ReAct 并返回结果，
  首次请求 messages 只有 `['system', 'user']`。
- 真实模型烟测（用户当前 provider `coco`）：`echo` 管道输入可正常对话并退出，ExitCode=0。
- 工具边界烟测：`exec` 正常执行；`exec` 运行 `playwright-cli` 被拦截；
  `read_file` 越出 workspace 被拒绝；`browser_*` 在 session 未打开时返回失败 ToolResult 而不是抛异常。
- 测试套件已按用户要求删除，不再运行。

## 已知问题

- 没有任何对话记忆：模型看不到上一轮消息，多轮任务需要用户在同一条消息里说清。
- 删除 Guardrails 后没有工具级审批 / 拦截；`exec`、`write_file` 可被模型直接调用。
- 删除浏览器可靠性层后，浏览器失败不再自动恢复，重试完全由模型判断。
- 没有测试目录，回归只能靠手工烟测。
- `config/config.json` 是本机真实配置（含明文 API Key），已被 `.gitignore` 忽略。
  其中 `browser.headed` / `browser.session_map` 两段已无人读取，属历史遗留。

## 下一步

- 无进行中的开发任务。

## 不要重复进行的工作

- 不要把 Evals、Guardrails、Messaging/Feishu、长期记忆、Skills 重新引入。
- 不要把 `storage/`、`core/concurrency.py`、`browser_reliability.py` 或任务状态机加回来。
- 不要把 `tests/`、`workspace/sessions/`、`session.py` 恢复；用户明确说明不需要。
- 不要把 `mybot/core/`、`mybot/mcp/`、`mybot/tracing/`、`mybot/workspace/`、
  `mybot/tools/browser/` 这些包目录加回来；现在是单文件模块布局。
- 不要重新加回 `max_context_chars`、`max_tool_result_chars`、`trust_annotations`。
- 不要把 `AI_HANDOFF.md` 挪回 `docs/`。
- 不要提交 `config/config.json`。
