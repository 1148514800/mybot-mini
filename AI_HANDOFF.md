# AI Handoff

## 当前目标与状态

第三轮裁剪完成：在"只保留 Agent 基本功能"的基础上，继续删除用户不需要的会话历史与
全部 Skills。当前仓库只保留：CLI 对话、ReAct 循环、统一 Tool 执行、Browser 工具、
MCP、Tracing。

## 已完成内容与修改文件

**本轮删除**

- `mybot/session.py`：不再保留历史会话，程序每次启动都是全新对话。
- `mybot/skills/`（`loader.py`、`__init__.py`）与 `workspace/skills/`（全部 4 个 skill，
  60 个受版本控制文件）。
- `docs/` 目录：`AI_HANDOFF.md` 移到仓库根目录。

**本轮改造**

- `mybot/agent/loop.py`：`AgentLoop.__init__` 不再接收 `sessions`；
  `handle_inbound_message()` 直接由当前这条用户消息构建 messages，不再读写会话历史；
  删除 `loaded_skills` 相关参数与状态。
- `mybot/agent/context.py`：`build_messages(user_message)` 只返回 System + 当前用户消息，
  不再拼接 history；删除 `SkillsLoader` 与 System Prompt 中的 Skills 段落。
- `mybot/agent/tool_execution.py`：删除 `loaded_skills` 字段、Skill 去重分支与
  `skill_path()`。
- `mybot/core/app.py`：不再构建 `SessionManager`。
- `mybot/core/config.py`、`config/config.example.json`：删除 `llm.max_recent_messages`。
- `mybot/workspace/bootstrap.py`：不再创建 `workspace/sessions/`。
- `mybot/main.py`：ASCII 架构图删除 Skills。
- `AGENTS.md`：`docs/AI_HANDOFF.md` 全部改为 `AI_HANDOFF.md`。
- `.gitignore`：删除已失效的 `workspace/sessions/`、`workspace/state/`。
- `README.md`、`mybot/tools/browser/README.md`：同步裁剪后的架构。

## 验证结果

- `python -m compileall -q mybot`：通过。
- `uv run --with pyflakes python -m pyflakes mybot`：仅剩 3 条 HEAD 已存在的历史告警
  （`context.py` 的 datetime/dataclass、`tools/browser/base.py` 的 DEFAULT_SESSION）。
- 导入检查：`mybot`、`mybot.main`、`mybot.core.app`、`mybot.agent`、`mybot.tools`、
  `mybot.tracing`、`mybot.mcp`、`mybot.workspace` 全部正常。
- 端到端烟测（假 LLM + 真实 `exec`）：首次请求的 messages 只有 `['system', 'user']`，
  System Prompt 不含 Skills；`workspace/` 下只生成 `instructions/`，不再产生
  `sessions/`。
- CLI 读循环烟测：`run()` 正常读入、回复、`exit` 退出。
- 测试套件已按用户要求删除，不再运行。

## 已知问题

- 删除 Guardrails 后没有工具级审批 / 拦截；`exec`、`write_file` 可被模型直接调用。
- 删除浏览器可靠性层后，浏览器失败不再自动恢复，重试完全由模型判断。
- 没有任何对话记忆：模型看不到上一轮消息，多轮任务需要用户在同一条消息里说清。
- 没有测试目录，回归只能靠手工烟测。
- `config/config.json` 是本机真实配置（含明文 API Key），已被 `.gitignore` 忽略。

## 下一步

- 无进行中的开发任务。

## 不要重复进行的工作

- 不要把 Evals、Guardrails、Messaging/Feishu、长期记忆重新引入。
- 不要把 `storage/`、`core/concurrency.py`、`browser_reliability.py` 或任务状态机加回来。
- 不要把 `tests/`、`workspace/sessions/`、`session.py`、`mybot/skills/`、
  `workspace/skills/` 恢复；用户明确说明不需要。
- 不要把 "会话历史" 类功能加回 `AgentLoop`；当前上下文只有 System Prompt 与当前用户消息。
- 不要把 `AI_HANDOFF.md` 挪回 `docs/`。
- 不要提交 `config/config.json`。
