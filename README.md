# MyBot

MyBot 是一个运行在本地的 AI Agent。它通过 OpenAI 兼容接口调用大模型，提供命令行对话；Agent 还可以使用本地文件、会话和浏览器自动化工具。

本文面向第一次接触本项目的用户。按照“快速开始”完成后，你就可以在命令行中与 Bot 对话。

## 功能概览

- 命令行（CLI）对话
- 基于 `playwright-cli` 的浏览器操作
- 单会话上下文记忆（对话历史持久化到 `workspace/sessions/`）
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
Gateway started. Channel: cli
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
| `llm.rate_limit_retries` | 遇到限流时自动重试次数；每次等待约 60 秒，程序硬上限为 10 |
| `llm.max_react_steps` | 一次请求最多执行多少轮 Agent/工具循环；程序硬上限为 30 |
| `llm.max_context_chars` | 发送给模型的 Context 目标字符预算，默认 `60000`；System、核心指令和当前任务 anchor 超出时允许 soft overflow |
| `llm.max_recent_messages` | 历史消息数量上限，默认 `12` |
| `llm.max_tool_result_chars` | 单条 Tool Result 在模型 Context 中的字符上限，默认 `8000` |
| `workspace.path` | 工作区路径，默认是 `./workspace` |
| `tracing.trace_dir` | Trace JSON 保存目录；默认 `null`，只保存在内存中 |
| `mcp.enabled` | 是否在 Gateway 启动时连接并发现 MCP Tools；默认 `false` |
| `mcp.servers.*.required` | MCP Server 失败时是否阻止 Gateway 启动 |
| `mcp.servers.*.trust_annotations` | 是否在 Trace 中记录 MCP Tool annotation；默认 `false` |
| `debug.show_internal_process` | 是否输出 Agent 的内部 trace |

修改 JSON 后需要重启程序才会生效。

Context compaction 只发生在每次 LLM request 前。Tool call 及其全部 tool result 作为原子单元按原始顺序一起保留或删除；孤立、缺失或重复配对不会发送给模型。`max_context_chars` 是 soft target，必要的系统指令和当前任务输入超出目标时会保留，并在 Trace 中标记 overflow。

对话历史按 session 写入 `workspace/sessions/`，重启后继续在同一 session 中对话即可复用上下文。超出 `max_context_chars` 或 `max_recent_messages` 的历史会被压缩；需要长期保留的信息应写入项目文件，而不是依赖聊天记录。`exec` 不是 OS sandbox。

## 运行数据和项目结构

```text
config/
  config.json
  config.example.json
mybot/
  main.py                 # 程序入口
  agent/                  # Agent orchestration 与统一 Tool 执行
  mcp/                    # MCP 配置、官方 Client 生命周期、命名和 Tool Adapter
  tracing/                # Run、Step、LLM、Tool trace 与 timeline replay
  core/                   # 配置和应用组装
  session.py              # 会话与对话历史持久化
  tools/                  # Agent 可调用的工具
workspace/
  instructions/           # AGENTS.md、SOUL.md、USER.md、TOOLS.md
  skills/                 # 本地 Skills
  sessions/               # 对话历史（JSONL）
  browser_profiles/       # Runtime 管理的浏览器 profile
  runs/                   # 可选的持久化 Trace
```

`workspace/sessions/`、`workspace/browser_profiles/` 和 `workspace/runs/` 会被程序自己写入；
删除 `workspace/sessions/` 会丢失对话历史，删除 `browser_profiles/` 会丢失浏览器登录状态。

## Agent Runtime 执行架构

Gateway 以单个 CLI 会话运行。退出时会关闭 LLM client 和 MCP Server 连接。

Browser 是进程级共享资源，采用独占 lease：首个 `browser_open` 或 `browser_attach` 成功的调用
成为 owner；其他调用会返回 `browser_ownership_conflict`，不会执行真实命令。
owner 必须成功调用 `browser_close` 才会释放 lease。

所有 Agent-visible Tool Call 都进入同一个执行边界：

~~~text
AgentLoop
    ↓
ToolExecutionPipeline
    ├── Tool lookup
    ├── Arguments normalization / schema validation
    ├── execution guard / runtime preconditions
    ├── ToolRegistry → Tool
    ├── ToolResult / BrowserResult normalization
    └── Trace update
~~~

未知 Tool、非法 JSON、缺少必填参数或参数类型错误统一转换为失败的 ToolResult，不会使
AgentLoop 崩溃。

AgentLoop 只保留一条 ReAct 主循环：调用模型、执行 Tool、把结果回灌上下文，直到模型
给出最终回复或达到 `max_react_steps`。任务状态不跨 Run 持久化，Runtime 不保存
Tool Arguments、浏览器输入或 secret。

## Tracing

每次 Agent 请求都会在内存中生成独立 Trace，记录 Run、Agent Step、LLM 调用和
Tool 调用。Tool 参数及 metadata 中常见的 password、token、api_key、authorization、
cookie、secret 等字段会自动脱敏；`browser_type.text` 也按语义隐藏，避免普通字段名
承载密码时泄漏。Tool 输出预览最多保留 2000 字符。开启
`debug.show_internal_process` 后，终端中的 Tool 参数和结果同样经过这套脱敏。
Trace summary 不会进入 LLM 上下文。

每次 Run 记录自己的 `status`（success、max_steps 或 failed）。旧 Trace 缺少新增字段时
仍可读取和 Replay。

默认 `tracing.trace_dir` 为 `null`，不会写入磁盘。需要在 Run 完成后保存 JSON 时，
可在本机 `config/config.json` 中设置：

```json
{
  "tracing": {
    "trace_dir": "./workspace/runs"
  }
}
```

Replay 只读取已有 Trace 并输出 timeline，不会再次调用模型或真实 Tool。

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
        "max_output_chars": 12000
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

Tool annotation（`readOnlyHint`、`destructiveHint`、`idempotentHint`、`openWorldHint`）
会作为 metadata 记录到 Trace，供人工审查；Runtime 当前不对 MCP Tool 施加独立策略。

MCP 文本和 `structuredContent` 会转换为 `ToolResult`；图片、音频和 Resource 只返回
可读 placeholder，不把 base64 塞入模型上下文。输出默认限制为 12000 字符，每次调用
有独立 timeout，不做自动 retry。外部内容始终被视为不可信数据，其中的指令不能覆盖
System 或 User 指令，也不能自行获得额外 Tool 权限。

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
- `browser_eval`：结构化工具无法满足时的任意 JavaScript fallback
- `browser_close`：关闭 session

未明确指定时，Agent 默认调用 `browser_open` 并使用 `managed_browser`。只有消息
明确包含“本地浏览器”“当前 Chrome”“已打开的浏览器”等意图时，才调用
`browser_attach` 并使用 `local_browser`。每轮请求会锁定一种模式，不会因上一轮
的活动 session 而串用浏览器，也不会在一种模式失败后自动切换到另一种模式。
同一 task 内浏览器成功初始化一次后，后续 Run 会复用原 session。查找文本、输入框和
按钮应优先使用 snapshot、links 和 inspect。Snapshot 中的 `[ref=e102]` 在点击参数中
应写为 `e102`，不能写成 `ref=e102`。

即使 `playwright-cli` 进程退出码为 0，输出中的明确 `### Error` block 也会转换为
`BrowserResult(success=False)`。网页自身的 Console Error 只作为页面数据保留，不会
被误判成 Tool 执行失败。

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

删除 `.venv` 不会删除源码、配置模板或 `workspace` 数据；但请不要随意删除 `workspace`，其中可能包含你的会话记录。

## 安全提醒

- 不要把 API Key 或浏览器登录状态提交到 Git。
- `workspace/browser_profiles/` 包含托管浏览器登录数据，已经被 `.gitignore` 忽略。
- `config/config.json` 已被 `.gitignore` 忽略，但提交前仍应检查 `git diff`。
- 如果密钥曾经意外公开，请立即在对应服务商后台撤销并重新生成。
