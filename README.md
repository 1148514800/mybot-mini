# MyBot

MyBot 是一个运行在本地的 AI Agent。它通过 OpenAI 兼容接口调用大模型，默认提供命令行对话，也可以连接飞书；Agent 还可以使用本地文件、记忆、会话和浏览器自动化工具。

本文面向第一次接触本项目的用户。按照“快速开始”完成后，你就可以在命令行中与 Bot 对话。

## 功能概览

- 命令行（CLI）对话
- 可选的飞书机器人通道
- 基于 `playwright-cli` 的浏览器操作
- 持久化会话和长期记忆
- 确定性的 Tool Policy、风险分级和 Human-in-the-loop 审批
- 跨 CLI / 飞书消息的 Approval 与普通 Clarification Pause / Resume
- 版本化 SQLite Active Task Checkpoint 与保守的进程重启恢复
- 持久化继续状态采用删除成功后再执行的 fail-closed 消费语义，并校验澄清回答者与最近任务 TTL
- 浏览器错误分类、有限恢复、任务预算、完成证据与最近任务续接
- 基于官方 MCP Python SDK v2 的 stdio 和 Streamable HTTP 外部工具运行时
- 从 `workspace/skills/` 自动加载本地 Skills
- 支持 SiliconFlow、OpenAI 以及其他 OpenAI 兼容服务
- 使用 `AsyncOpenAI` 发起非阻塞模型请求，并提供默认 60 秒总超时

## 快速开始（Windows）

### 1. 准备软件

需要安装：

- Python **3.12 或更高版本**。项目在 `pyproject.toml` 中要求 `>=3.12`。
- Node.js（建议安装 LTS 版本）。浏览器工具需要它运行 `playwright-cli`。
- 一个 OpenAI 兼容的大模型 API Key。

安装后，在 PowerShell 中检查版本：

```powershell
python --version
node --version
npm --version
```

Python 版本必须是 `3.12.x` 或更高。如果电脑同时安装了多个 Python，也可以使用 Python Launcher：

```powershell
py -3.12 --version
```

### 2. 安装 `playwright-cli`（浏览器功能需要）

```powershell
npm install -g @playwright/cli@latest
playwright-cli --version
```

如果你暂时不使用浏览器功能，这一步可以稍后再做；不安装时，普通 CLI 对话仍然可以运行，但调用浏览器工具会提示 `playwright-cli was not found in PATH`。

### 3. 创建 Python 虚拟环境

在项目根目录（能看到 `pyproject.toml` 的目录）打开 PowerShell，执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

看到命令行前出现 `(.venv)`，表示虚拟环境已经激活。

如果 PowerShell 阻止激活脚本，不需要修改系统策略，直接使用虚拟环境中的 Python 即可：

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
```

### 4. 创建配置文件

项目不会自动生成包含密钥的配置文件。先复制示例配置：

```powershell
Copy-Item config\config.example.json config\config.json
```

然后用编辑器打开 `config\config.json`，至少修改当前模型提供商对应的 `api_key`。示例配置默认使用 SiliconFlow：

```json
{
  "llm": {
    "provider": "siliconflow",
    "providers": {
      "siliconflow": {
        "api_key": "替换为你的 SiliconFlow API Key",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "Qwen/Qwen3-235B-A22B-Instruct-2507"
      }
    }
  }
}
```

也可以使用 OpenAI：

```json
{
  "llm": {
    "provider": "openai",
    "providers": {
      "openai": {
        "api_key": "替换为你的 OpenAI API Key",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4.1-mini"
      }
    }
  }
}
```

实际使用时，建议保留 `config/config.example.json` 的完整结构，只修改以下字段：

- `llm.provider`：必须与 `llm.providers` 下的名称一致。
- `llm.providers.<提供商>.api_key`：你的 API Key。
- `llm.providers.<提供商>.base_url`：服务商的 OpenAI 兼容接口地址。
- `llm.providers.<提供商>.model`：服务商提供的模型名称。
- `feishu.enabled`：不使用飞书时保持 `false`。

`config/config.json` 已被 `.gitignore` 忽略，不应把真实 API Key 提交到 Git。也可以使用环境变量覆盖密钥：

```powershell
$env:OPENAI_API_KEY = "你的 API Key"
$env:OPENAI_BASE_URL = "https://api.openai.com/v1"
$env:MYBOT_MODEL = "gpt-4.1-mini"
```

环境变量只对当前 PowerShell 窗口生效。程序读取配置时，环境变量优先于 JSON 配置。

### 5. 启动项目

如果虚拟环境已激活：

```powershell
python mybot\main.py
```

如果没有激活虚拟环境：

```powershell
.\.venv\Scripts\python.exe mybot\main.py
```

启动成功后会看到类似输出：

```text
Feishu channel disabled. Set feishu config to enable it.
Gateway started. Channels: ['cli']
You:
```

在 `You:` 后输入问题并按 Enter。输入 `exit` 或 `quit` 退出程序。

## Linux / macOS

### 1. 安装依赖

以 Ubuntu/Debian 为例：

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv nodejs npm
npm install -g @playwright/cli@latest
```

确认版本：

```bash
python3.12 --version
node --version
playwright-cli --version
```

### 2. 创建环境并安装项目

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
cp config/config.example.json config/config.json
```

编辑 `config/config.json` 填入 API Key 后启动：

```bash
python mybot/main.py
```

浏览器自动化默认启动带持久化登录 profile 的 MyBot 独立 Chrome；只有用户明确
要求使用本地、当前或已打开的浏览器时，才连接用户现有的 Chrome。无桌面环境不
支持这两种模式。

## 使用 `uv` 安装（可选）

如果你已经安装了 [uv](https://docs.astral.sh/uv/)，可以用锁定文件安装依赖：

```bash
uv sync
```

然后使用 uv 运行：

```bash
uv run python mybot/main.py
```

`uv sync` 负责 Python 依赖；`playwright-cli` 仍然需要通过 Node.js/npm 单独安装。

## 飞书机器人（可选）

不配置飞书时，程序只启动本地 CLI，这是默认行为。

要启用飞书：

1. 在飞书开放平台创建企业自建应用，并启用机器人能力。
2. 取得应用的 `App ID` 和 `App Secret`。
3. 在 `config/config.json` 中填写并启用：

   ```json
   {
     "feishu": {
       "enabled": true,
       "app_id": "你的 App ID",
       "app_secret": "你的 App Secret"
     }
   }
   ```

4. 在飞书应用后台配置机器人接收消息所需的权限和事件订阅，然后重新启动程序。

启用成功后，启动日志中会出现 `feishu` 通道。飞书连接使用长连接模式，通常不需要额外配置公网回调地址。

## 配置字段说明

```text
config/
  config.json          # 本机真实配置，不提交到 Git
  config.example.json  # 配置模板
```

常用字段：

| 字段 | 作用 |
|---|---|
| `llm.provider` | 当前使用的模型提供商名称 |
| `llm.providers.*.api_key` | 对应提供商的 API Key |
| `llm.providers.*.base_url` | OpenAI 兼容接口地址 |
| `llm.providers.*.model` | 模型名称 |
| `llm.max_completion_tokens` | 单次回复的最大 token 数 |
| `llm.request_timeout_seconds` | 单次模型请求的总超时秒数，默认 `60`；超时不会阻塞其他异步通道 |
| `llm.max_react_steps` | 一次请求最多执行多少轮 Agent/工具循环；程序硬上限为 30 |
| `llm.max_context_chars` | 发送给模型的 Context 目标字符预算，默认 `60000`；System、核心指令和当前用户输入超出时允许 soft overflow |
| `llm.max_recent_messages` | 历史消息数量上限，默认 `12` |
| `llm.max_tool_result_chars` | 单条 Tool Result 在模型 Context 中的字符上限，默认 `8000` |
| `llm.max_memory_chars` | Memory 摘要在模型 Context 中的字符上限，默认 `8000` |
| `llm.rate_limit_retries` | 遇到限流时自动重试次数；每次等待约 60 秒，程序硬上限为 10 |
| `browser_runtime.max_open_attempts` | 每个 task 的 `browser_open/browser_attach` 尝试上限，默认 `1` |
| `browser_runtime.max_consecutive_tool_failures` | 同一浏览器 Tool 连续失败上限，默认 `2` |
| `browser_runtime.max_failed_action_retries` | 同一失败 Action 的额外重试次数，默认 `1` |
| `browser_runtime.max_eval_fallbacks` | 每个 task 的 `browser_eval` fallback 上限，默认 `1`；Policy 确认仍生效 |
| `browser_runtime.max_recovery_steps` | 每个 task 的自动恢复步骤上限，默认 `2` |
| `guardrails.approval_ttl_seconds` | 待确认操作的有效期，默认 `600` 秒；过期后必须重新发起 |
| `checkpoint.enabled` | 是否持久化 Active Task Checkpoint，默认 `true`；设为 `false` 时保持纯内存模式 |
| `checkpoint.recent_task_ttl_seconds` | 最近 Browser Task checkpoint 的有效期，默认 `86400` 秒 |
| `feishu.enabled` | 是否启用飞书通道 |
| `workspace.path` | 工作区路径，默认是 `./workspace` |
| `tracing.trace_dir` | Trace JSON 保存目录；默认 `null`，只保存在内存中 |
| `mcp.enabled` | 是否在 Gateway 启动时连接并发现 MCP Tools；默认 `false` |
| `mcp.servers.*.required` | MCP Server 失败时是否阻止 Gateway 启动 |
| `mcp.servers.*.trust_annotations` | 是否允许可信的 `readOnlyHint` 自动放行；默认 `false` |
| `debug.show_internal_process` | 是否输出 Agent 的内部 trace |

修改 JSON 后需要重启程序才会生效。

## 运行数据和项目结构

```text
config/
  config.json
  config.example.json
mybot/
  main.py                 # 程序入口
  agent/                  # Agent orchestration、统一 Tool 执行和显式任务状态
  guardrails/             # Tool Policy、审批和普通澄清的内存状态
  mcp/                    # MCP 配置、官方 Client 生命周期、命名和 Tool Adapter
  tracing/                # Run、Step、LLM、Tool trace 与 timeline replay
  evals/                  # 确定性 Eval、FakeLLM runner 和文本报告
  core/                   # 配置和应用组装
  messaging/              # CLI、飞书和消息总线
  storage/                # 会话、记忆和版本化 SQLite checkpoint
  tools/                  # Agent 可调用的工具
workspace/
  instructions/           # AGENTS.md、SOUL.md、USER.md、TOOLS.md
  skills/                 # 本地 Skills
  memory/                 # 长期记忆
  sessions/               # 对话历史（JSONL）
  browser_profiles/       # Runtime 管理的浏览器 profile
  checkpoints/            # Runtime 管理的 Active Task SQLite checkpoint
  runs/                   # 可选的持久化 Trace
evals/                    # 离线 EvalCase JSON 数据
```

`memory/`、`sessions/`、`browser_profiles/`、`checkpoints/` 和 `runs/` 是 Runtime 管理目录，普通
`write_file` 会直接阻止对这些目录的修改；记忆变更必须使用 `memory_write` 或
`memory_delete`。`instructions/` 以及 `AGENTS.md`、`SOUL.md`、`USER.md`、`TOOLS.md`
等指令文件仍需要明确确认。目录删除会丢失对应状态，请先备份。

## Agent Runtime 执行架构

所有 Agent-visible Tool Call，包括正常 ReAct、Approval Resume 后的冻结动作以及
同批次剩余调用，现在都进入同一个执行边界：

~~~text
AgentLoop
    ↓
ToolExecutionPipeline
    ├── Tool lookup
    ├── Arguments normalization / schema validation
    ├── ToolPolicy
    ├── Approval authorization / runtime preconditions
    ├── ToolRegistry → Tool
    ├── ToolResult / BrowserResult normalization
    └── Trace + browser task state update
~~~

正常调用在 Policy ALLOW 后执行；REQUIRE_CONFIRMATION 只冻结动作并暂停，不会提前
执行。用户确认后，Pipeline 执行 PendingApproval 中原样保存的 Tool 和 Arguments，
不会重新请求模型生成调用；Tool lookup、参数校验、BLOCK 规则、Runtime-managed path
保护、Approval TTL、sender/task 绑定和 browser precondition 仍会重新检查。对于受支持的
高风险 Browser Approval，Runtime 会在冻结动作执行前主动调用同一 session 的只读
`browser_snapshot`，再验证当前 URL、目标 ref 及其 action-relevant 角色/语义；无法读取或
无法可靠验证时 fail closed。验证不要求整份 snapshot 字符串完全一致，因此页面中的无关
动态文本不会单独使审批失效。未知 Tool、非法 JSON、缺少必填参数或参数类型错误统一转换为
失败的 ToolResult，不会使 AgentLoop 崩溃。

AgentTaskState 显式表示 new、running、waiting_approval、
waiting_clarification、waiting_verification、completed、failed、
max_steps 和 cancelled。Trace 的 status 是本次 Runtime Run 状态，
task_status 是跨 pause/resume 的用户任务状态；因此允许 Runtime 正常结束但任务仍为
waiting_verification。Task State 只保存小型状态和关联 ID，不保存 Tool Arguments、
浏览器输入或 secret。

等待 Approval、Clarification、Verification 的 Active Task State 与 Recent Browser Task
会保存到 `workspace/checkpoints/active_tasks.sqlite3`。存储层使用 SQLite transaction、
明确的 JSON-compatible payload 和 `schema_version=1`，不使用 pickle；每个 session 的
active checkpoint 原子覆盖。任务进入 completed、failed、max_steps 或 cancelled 后会清除
active checkpoint，Recent Browser Task 则按独立 TTL 保留，供用户纠正或继续。

重启只重建等待管理器和小型任务状态，不调用模型，也不执行 Tool。确认恢复的 Approval 时，
Runtime 仍重新检查 TTL、sender、task、Tool schema、当前 Policy 和适用的 fresh browser
precondition。消费 Approval 时会在任何副作用前先删除 active checkpoint；如果之后进程崩溃，
该动作不会自动重放，用户需要重新发起。重启前同一模型批次中尚未独立批准的其余 Tool Call
也会跳过并交给模型重新评估。

Checkpoint 写入前会递归清理 password、token、cookie、authorization、secret、API key
以及 `browser_type.text`；需要丢弃原始参数才能安全落盘的 Approval 会标记为
non-resumable，重启后即使确认也不会执行。持久化 browser snapshot/session 状态只视为历史
上下文：恢复后的 Clarification、Verification 和 Recent Task 必须重新连接并读取 live state；
Browser Approval 仅保留执行 fresh-state 比较所需的最小 URL/目标语义。无法解析、row identity
不一致或 schema 不受支持的 checkpoint 会 fail closed。将 `checkpoint.enabled` 设为 `false`
可完全关闭 SQLite 文件并保留原有纯内存行为。

## Tracing 与离线 Evals

每次 Agent 请求都会在内存中生成独立 Trace，记录 Run、Agent Step、LLM 调用和
Tool 调用。Tool 参数及 metadata 中常见的 password、token、api_key、authorization、
cookie、secret 等字段会自动脱敏；`browser_type.text` 也按语义隐藏，避免普通字段名
承载密码时泄漏。Tool 输出预览最多保留 2000 字符。开启
`debug.show_internal_process` 后，终端中的 Tool 参数和结果同样经过这套脱敏。
Trace summary 不会进入 LLM 上下文。

每个新用户目标会生成一个 `task_id`。如果任务因 Approval 或 Clarification 分成多个
Run，每个 Run 仍各自保存一个 JSON，但顶层 `task_id` 和兼容字段
`metadata.task_id` 保持相同，并通过 `resumed_from_run_id` 指向前一个 Run。顶层
`task_status` 与 Run 自身的 `status` 分开记录。明显针对最近浏览器任务的纠正也沿用
同一 `task_id`，并在 Trace 中写入 `continuation=true`。旧 Trace 没有新增字段时仍可
读取和 Replay。

默认 `tracing.trace_dir` 为 `null`，不会写入磁盘。需要在 Run 完成后保存 JSON 时，
可在本机 `config/config.json` 中设置：

```json
{
  "tracing": {
    "trace_dir": "./workspace/runs"
  }
}
```

运行不访问真实 LLM、网络或浏览器的确定性 FakeLLM Eval：

```powershell
uv run python -m mybot.evals.runner
```

Eval 数据位于根目录 `evals/`，当前覆盖 Tool Selection、Browser Navigation、
Failure Recovery、Policy Guardrails、MCP Tools、Runtime Efficiency 和 Browser
Reliability。Replay 只读取已有 Trace 并输出
timeline，不会再次调用模型或真实 Tool。

## Guardrails 与 Human-in-the-loop

每个模型提出的 Tool Call 都会由 `ToolExecutionPipeline` 完成 Tool lookup、参数解析、
schema 校验和浏览器 session 归一化，再进入 `ToolPolicy`。Policy 在
`ToolRegistry.execute()` 前给出独立的风险等级和执行决策：

```text
Proposed / Frozen Approved Tool Call
        ↓
ToolExecutionPipeline
        ↓
    ToolPolicy
        ↓
ALLOW / REQUIRE_CONFIRMATION / BLOCK
        ↓
   ToolRegistry（仅 ALLOW 或有效 Approval 授权的 exact action）
```

- 自动执行：文件读取、页面读取与导航、能够在最新快照中精确识别且无危险语义的普通
  点击、`browser_type(submit=false)`、普通工作区文件写入、记忆写入，以及严格
  allowlist 完整匹配的 `python --version`、`git status --short`、`git diff --stat`、
  `git log -5`、`git show HEAD`、`pwd` 等只读 Shell 查询。
- 要求确认：`browser_eval`、`browser_type(submit=true)`、`browser_press` 的 Enter/
  Space、最新快照中不存在的 ref、长期记忆删除、敏感配置或 instruction 文件写入、
  删除/移动/安装/提交等会改变状态的 Shell 命令，以及快照中明确标记为删除、付款、
  发布、发送等高影响动作的浏览器点击。未知 Shell 命令也采用保守确认策略。
- 直接阻止：高置信度识别到的系统级破坏命令，例如删除文件系统根目录、格式化磁盘、
  关机或重启，以及普通 `write_file` 对 Runtime 管理目录的覆盖。被阻止的调用不会
  进入 Tool Registry。

Exec allowlist 匹配的是整条命令；包含 `&&`、`||`、`;`、`|`、重定向、换行、反引号、
`$(...)` 等 shell control syntax 的命令不会因为安全前缀而自动放行。`ExecTool` 默认以
Agent workspace 作为 `cwd`，但这只确定相对路径的起点，不限制进程能够访问的操作系统
资源，也不是 sandbox。

需要确认时，本轮 Run 以 `awaiting_confirmation` 结束，CLI 或飞书会显示 Tool、风险、
原因、经过脱敏的具体动作预览和 Approval ID。回复 `确认`、`继续`、`同意`、`执行`、
`yes`、`y` 或 `approve` 会批准当前会话中那个确切的 Tool 和参数，并且只执行一次；
回复 `取消`、`拒绝`、`不要执行`、`停止`、`no`、`n` 或 `deny` 会取消它。其他回复会
取消旧审批并作为新的正常任务处理。审批按 `channel:chat_id` 关联 Conversation Session，
同时单独绑定原始 `sender_id`；群聊中的其他用户不能批准或拒绝该操作，也不会消费它。
审批默认 10 分钟过期，过期 Trace 记录 `approval_status=expired`。启用 checkpoint 时，等待
审批可跨进程重启恢复，但不会因重启自动执行；过期项在恢复时直接丢弃。关闭 checkpoint 时，
审批仍仅保存在内存中。

Policy 的 `risk_level`、`policy_decision`、`policy_rule`、`policy_reason`、`approval_id`
和 `approval_status` 会写入现有 Tool Call Trace。Browser live precondition 的内部只读
snapshot 另以 `runtime_internal`、`runtime_precondition_check`、`precondition_type`、
`precondition_result` 和可选 `precondition_reason` 标记，不伪装成模型提出的 Tool Call，
也不会再次触发 Approval。所有 Trace 继续使用相同的敏感字段脱敏。
`ToolPolicy` 是 Runtime Safety Layer，不是操作系统级 sandbox。它提供确定性、可测试的
应用层执行边界，但不能替代容器、账户权限、文件系统 ACL 或其他 OS 隔离机制。

## 普通 Clarification 与任务连续性

缺少参数、等待登录或遇到同名好友等普通歧义时，Agent 调用
`request_user_input`。当前 Run 以 `awaiting_clarification` 结束，并把 messages、
browser mode、已加载 Skill 和必要的浏览器历史状态保存在按
session 隔离的 `PendingClarification` 中。用户下一条回复会消费该状态并继续原任务，
不会重新构建 System Prompt 或重复读取同一个 Skill。进程内恢复可以复用已有 Browser
Session；跨重启恢复不会把持久化 session/snapshot 当作 live state，必须重新连接并读取页面。

Clarification 与高风险 Approval 是两套独立状态：普通回答不会批准危险 Tool，审批仍然
要求确定性的确认词并绑定 exact action。两种恢复流程会继承同一个 `task_id`；启用
checkpoint 时都可以跨重启继续，关闭时维持纯内存行为。

## MCP External Tool Runtime

MCP 默认关闭。启用后，Gateway 会在 AgentLoop 启动前使用官方 `mcp>=2,<3` Client
连接所有已启用 Server、完成协议协商和 `tools/list`，再把每个外部工具包装为现有
`Tool` 并注册到同一个 ToolRegistry。MyBot 不自行实现 JSON-RPC、initialize 或协议
版本分支，也不会读取 MCP Resources、Prompts 或 Server Instructions。

实际配置格式如下；密钥使用环境变量引用，不要写入仓库：

```json
{
  "mcp": {
    "enabled": true,
    "servers": {
      "local_demo": {
        "enabled": true,
        "transport": "stdio",
        "command": "python",
        "args": ["-m", "demo_mcp_server"],
        "env": {"DEMO_API_KEY": "${DEMO_API_KEY}"},
        "required": false,
        "trust_annotations": false,
        "tool_timeout_seconds": 30,
        "max_output_chars": 12000,
        "tool_policy": {
          "search": "allow",
          "create_item": "confirm",
          "delete_all": "block"
        }
      },
      "remote_demo": {
        "enabled": true,
        "transport": "streamable_http",
        "url": "http://127.0.0.1:8000/mcp",
        "headers": {
          "Authorization": "Bearer ${DEMO_MCP_TOKEN}"
        },
        "required": false,
        "trust_annotations": false,
        "tool_timeout_seconds": 30
      }
    }
  }
}
```

stdio Server 由官方 Client 启动为子进程，并在 Gateway 退出时通过 Client 生命周期关闭。
Streamable HTTP 使用官方 `streamable_http_client`；不支持 legacy SSE。`required=false`
的 Server 连接失败时会被跳过，其他 Server 和 Runtime 继续启动；`required=true` 失败
会终止启动。

发现的工具使用 `mcp__<server>__<tool>` namespace。非法字符和超长名称会确定性清理
并附加稳定 hash，collision 不会覆盖现有 Tool。输入 JSON Schema 尽量原样保留；无法
作为 Function Tool object schema 使用的工具会跳过并记入 Server Status。

外部 MCP Tool 默认视为敏感操作并要求确认。只有 `trust_annotations=true` 且 Tool
声明 `readOnlyHint=true` 时才会自动允许；`destructiveHint=true` 始终要求确认。
每个 Server 的 `tool_policy` 可按外部 Tool 原名显式设置 `allow`、`confirm` 或 `block`，
其优先级高于 annotation。需要确认的 MCP Tool 直接复用现有 PendingApproval、Session
隔离、exact-action 和 single-use 流程。

MCP 文本和 `structuredContent` 会转换为 `ToolResult`；图片、音频和 Resource 只返回
可读 placeholder，不把 base64 塞入模型上下文。输出默认限制为 12000 字符，每次调用
有独立 timeout，不做自动 retry。外部内容始终被视为不可信数据，不能修改 Policy 或
自行获得额外 Tool 权限。

## 浏览器工具

浏览器工具不是 Python 的 `playwright` 包，而是通过命令行调用 `playwright-cli`。常见工具包括：

- `browser_attach`：通过 CDP 连接已经打开并保留登录状态的本地 Chrome
- `browser_open`：启动 MyBot 管理的独立 Chrome，并复用持久化登录状态
- `browser_goto`：在已有 session 中跳转
- `browser_tab`：列出、新建、选择或关闭标签页
- `browser_snapshot`：读取当前页面
- `browser_inspect`：通过 selector、text、role 或 placeholder 做只读 DOM 查询；调用者不能传 JavaScript
- `browser_verify`：通过 selector、text、role、placeholder 或 URL 验证最终后置条件；调用者不能传 JavaScript
- `browser_links`：按页面视觉顺序列出并去重链接，适合选择第 N 个结果
- `browser_click`、`browser_type`、`browser_press`：操作页面
- `browser_eval`：结构化工具无法满足时的任意 JavaScript fallback，始终要求确认
- `browser_close`：关闭 session

未明确指定时，Agent 默认调用 `browser_open` 并使用 `managed_browser`。只有消息
明确包含“本地浏览器”“当前 Chrome”“已打开的浏览器”等意图时，才调用
`browser_attach` 并使用 `local_browser`。每轮请求会锁定一种模式，不会因上一轮
的活动 session 而串用浏览器，也不会在一种模式失败后自动切换到另一种模式。
同一 task 内浏览器成功初始化一次后，后续 Run 会复用原 session。查找文本、输入框和
按钮应优先使用 snapshot、links 和 inspect。Snapshot 中的 `[ref=e102]` 在点击参数中
应写为 `e102`，不能写成 `ref=e102`。Policy 对 ref 做精确匹配：`e1` 不会匹配 `e10`；
ref 不在最新 snapshot 中时需要确认，而能够明确识别为普通导航的目标仍可自动执行。
带 `submit=true` 的输入和 Enter/Space 按键可能触发表单提交，因此也进入确认流程；
普通 `submit=false` 文本输入保持低风险自动执行。`browser_eval` 始终要求确认。

确认高风险 Browser Action 后，Runtime 会先读取 fresh snapshot：`browser_click` 验证
URL、ref 与目标角色/文本，`browser_type(submit=true)` 还要求目标保持为兼容输入控件，
`browser_eval` 验证 session 与 URL。当前 snapshot 不记录可靠的 active/focused element，
所以 Enter/Return/Space 审批在恢复时会保守拒绝，要求用户基于当前页面重新发起。目标消失、
目标语义变化、URL 变化、session 不匹配或 snapshot 刷新失败都不会执行原副作用动作。
这是一层有限的 live precondition validation，不是完整的网页 Transaction System 或
optimistic locking；Restart Recovery 不会把 checkpoint 中的 Browser 数据当作 live state。

即使 `playwright-cli` 进程退出码为 0，输出中的明确 `### Error` block 也会转换为
`BrowserResult(success=False)`。网页自身的 Console Error 只作为页面数据保留，不会
被误判成 Tool 执行失败。

### Browser Runtime Reliability

浏览器失败会在 `BrowserResult.metadata` 中提供稳定的 `error_type` 与 `recoverable`，
当前分类包括 `stale_target`、`target_not_found`、`ambiguous_target`、
`tool_syntax_error`、`page_timeout`、`navigation_failure`、`auth_required`、
`policy_blocked`、`budget_exceeded` 和 `unknown`。Runtime 对 stale/not-found target
最多自动刷新一次快照，再允许模型用新 ref 重试一次；歧义目标要求用 inspect 缩小，
必要时向用户澄清；同一个 syntax error 不会被原样重复执行。

`browser_click`、`browser_type` 和 Enter/Space 成功只表示动作调用成功。它们之后会把
任务置为 `verification_required`，模型必须调用 `browser_verify`，且结构化后置条件
实际满足后，Runtime 才把 Browser Task 标记为 `verified`。如果最终动作失败、超时、
被 Policy 阻止、仍待确认或验证失败，Runtime 会阻止“已完成/已发送/已发布”等完成式
声明；模型仍可诚实报告未完成，此时 Agent Run 可以正常结束，但 Trace 中的
`browser_completion_state` 仍明确记录任务未完成。

用户在同一 session 中说“你没有完成”“刚才没点成功”“继续”“不是这样”等明确纠正
最近任务时，Runtime 会复用原 `task_id`、browser mode/session、当前 URL、最新
snapshot、已加载 Skills、最近 Tool Results、完成状态和剩余预算。该机制只恢复上下文，
不等于 Approval；任何新的 `browser_eval` 或高风险点击仍照常经过 ToolPolicy。

启用 checkpoint 后 Recent Browser Task 可在配置 TTL 内跨重启恢复。此时只复用 task_id、
经过脱敏的消息和历史完成状态；browser session、URL 和 snapshot 会被明确标记为 stale，
后续动作必须读取 fresh state。过期 Recent Task 会从 SQLite 删除。

这些机制是有限的 Runtime Reliability Layer，不是浏览器 sandbox，也不做无限重试。

首次使用浏览器时可能会下载或初始化浏览器运行组件，请预留网络和磁盘空间。持久化 session 会保存到 Playwright 的运行目录中。

## 常见问题

### `Missing api_key`

当前 `llm.provider` 对应的配置没有 API Key。检查 `config/config.json` 中的提供商名称和 `api_key`，或设置 `OPENAI_API_KEY`。

### `Invalid JSON`

`config/config.json` 不是合法 JSON。检查逗号、双引号和括号；JSON 不支持注释。可以重新复制模板：

```powershell
Copy-Item config\config.example.json config\config.json -Force
```

### `playwright-cli was not found in PATH`

重新安装并检查 npm 全局命令目录是否在 PATH 中：

```powershell
npm install -g @playwright/cli@latest
playwright-cli --version
```

如果只需要普通 CLI 对话，可以暂时忽略这个问题。

### 浏览器无法打开

使用 `browser_attach` 时先确认本地 Chrome 已打开。使用 `browser_open` 时，首次
启动需要在 MyBot 的独立 Chrome 中手动登录，后续会复用
`workspace/browser_profiles/managed_browser`。两种模式都应先确认
`playwright-cli --version` 可用，失败时不会自动切换到另一种模式。

### `ModuleNotFoundError`

确认你使用的是项目虚拟环境中的 Python：

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe mybot\main.py
```

### `429`、`TPM limit reached` 或请求超时

这是模型服务的限流、额度或响应速度问题，不是项目安装失败。模型请求默认在 60 秒后以 `LLM request timeout after 60s` 结束，不会无限等待。检查 API 额度、模型名称和服务商限制；也可以按需调整 `llm.request_timeout_seconds` 或 `llm.rate_limit_retries`。

## 重新安装环境

需要彻底重建 Python 环境时，先退出正在运行的程序，再删除 `.venv` 并重新执行安装步骤：

```powershell
Remove-Item -Recurse -Force .venv
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

删除 `.venv` 不会删除源码、配置模板或 `workspace` 数据；但请不要随意删除 `workspace`，其中可能包含你的会话和记忆。

## 安全提醒

- 不要把 API Key、飞书 App Secret 或浏览器登录状态提交到 Git。
- `workspace/browser_profiles/` 包含托管浏览器登录数据，已经被 `.gitignore` 忽略。
- `config/config.json` 已被 `.gitignore` 忽略，但提交前仍应检查 `git diff`。
- 如果密钥曾经意外公开，请立即在对应服务商后台撤销并重新生成。
