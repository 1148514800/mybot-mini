# AI Handoff

## 当前目标

Phase 5：收敛 Agent Runtime 的执行安全边界，保持现有 Runtime Contract。

## 当前状态

已完成，等待后续阶段规划。

## 已完成内容

- Exec 自动允许改为整条命令严格 allowlist；shell control syntax、未知命令和状态变更命令不再静默放行。
- `ExecTool` 显式依赖 workspace，并以 workspace 作为 subprocess cwd；文档明确 cwd 不是 sandbox。
- 新增统一 workspace 路径分类，阻止普通 `write_file` 修改 `memory/`、`sessions/`、`browser_profiles/`、`runs/`，保留 instructions/config 写入确认。
- 浏览器 ref 改为精确匹配；未知 ref、submit 输入、Enter/Space 及其常见组合采用保守确认，普通输入和已识别安全点击仍自动执行。
- PendingApproval 绑定原始 sender、保持 single-use，并增加可配置的 600 秒默认 TTL；身份错配与过期均不执行并写入 Trace。
- Approval Prompt 展示脱敏后的实际动作；exec command、browser target/text/URL、write path 等可在确认前审查。
- Trace 与 internal debug 复用统一脱敏；补充 authorization/cookie/secret 等文本格式和 `browser_type.text` 语义脱敏。
- 增加安全单元测试和 4 个 Policy Evals；Eval loader 忽略 macOS `._*.json` sidecar。

## 修改文件

- `.gitignore`
- `mybot/agent/loop.py`
- `mybot/core/config.py`
- `mybot/evals/runner.py`
- `mybot/guardrails/__init__.py`
- `mybot/guardrails/approvals.py`
- `mybot/guardrails/clarifications.py`
- `mybot/guardrails/models.py`
- `mybot/guardrails/paths.py`（新增）
- `mybot/guardrails/policy.py`
- `mybot/tools/exec.py`
- `mybot/tools/file_tools.py`
- `mybot/tools/registry.py`
- `mybot/tracing/__init__.py`
- `mybot/tracing/tracer.py`
- `config/config.example.json`
- `evals/browser_reliability.json`
- `evals/policy_guardrails.json`
- `tests/test_agent_browser_reliability.py`
- `tests/test_agent_confirmation.py`
- `tests/test_approval_manager.py`
- `tests/test_eval_runner.py`
- `tests/test_exec.py`
- `tests/test_file_tools.py`（新增）
- `tests/test_guardrail_policy.py`
- `tests/test_llm_client.py`
- `tests/test_tracer.py`
- `README.md`

## 架构决策

- 保持 AgentLoop、ToolRegistry、ToolResult、BrowserResult、MCP 和 Provider 架构不变，只在线性执行入口补充确定性策略与少量状态传递。
- Runtime-managed 目录对普通 `write_file` 采用 BLOCK，并在 Policy 与 Tool 层复用同一分类函数做防御性校验。
- Approval sender identity 独立于 `channel:chat_id` Conversation Session，不改变群聊 session 语义。
- `browser_type.text` 在 Trace、debug 和审批预览中始终隐藏，避免仅凭参数名无法识别密码内容。

## 测试结果

- `uv run python -m unittest discover -s tests -v`：189 passed，1 skipped。
- `uv run python -m mybot.evals.runner`：43/43 passed，100%。
- 跳过项为需要显式启用本地 Chrome 的集成测试。

## 已知问题

- Browser task state 仍仅在进程内保存，未持久化。
- Approval / Clarification 重启后仍不能恢复。
- Browser session 尚未实现并发隔离。
- AgentLoop 职责仍偏重，本阶段未做大规模拆分。
- Context/token budget 与 Tool result context compression 尚未实现。
- 真实 LLM、真实站点和真实用户交互的任务级 E2E Eval 仍缺失。
- ToolPolicy 是应用层 Runtime Safety Layer，不是操作系统级 sandbox。

## 下一步

- 下一阶段优先设计可恢复的 task/approval/clarification 状态与 browser session 并发隔离，再评估 AgentLoop 分层和 context budget；不要在没有迁移方案时直接持久化当前内存对象。

## 不要重复进行的工作

- 不要恢复“安全命令前缀匹配”或“未知 browser ref 默认 ALLOW”的旧行为。
- 不要用 `channel:chat_id:sender_id` 替代现有 Conversation Session key；Approval identity 已单独绑定。
- 不要绕过 `memory_write` / `memory_delete` 直接写 Runtime memory 文件。
