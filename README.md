# MyBot

MyBot 是一个运行在本地的 AI Agent。它通过 OpenAI 兼容接口调用大模型，默认提供命令行对话，也可以连接飞书；Agent 还可以使用本地文件、记忆、会话和浏览器自动化工具。

本文面向第一次接触本项目的用户。按照“快速开始”完成后，你就可以在命令行中与 Bot 对话。

## 功能概览

- 命令行（CLI）对话
- 可选的飞书机器人通道
- 基于 `playwright-cli` 的浏览器操作
- 持久化会话和长期记忆
- 确定性的 Tool Policy、风险分级和 Human-in-the-loop 审批
- 跨 CLI / 飞书消息的 Pause / Resume
- 从 `workspace/skills/` 自动加载本地 Skills
- 支持 SiliconFlow、OpenAI 以及其他 OpenAI 兼容服务

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
| `llm.max_react_steps` | 一次请求最多执行多少轮 Agent/工具循环；程序硬上限为 30 |
| `llm.rate_limit_retries` | 遇到限流时自动重试次数；每次等待约 60 秒，程序硬上限为 10 |
| `feishu.enabled` | 是否启用飞书通道 |
| `workspace.path` | 工作区路径，默认是 `./workspace` |
| `tracing.trace_dir` | Trace JSON 保存目录；默认 `null`，只保存在内存中 |
| `debug.show_internal_process` | 是否输出 Agent 的内部 trace |

修改 JSON 后需要重启程序才会生效。

## 运行数据和项目结构

```text
config/
  config.json
  config.example.json
mybot/
  main.py                 # 程序入口
  agent/                  # Agent 循环和上下文构建
  guardrails/             # Tool Policy、风险模型和内存审批状态
  tracing/                # Run、Step、LLM、Tool trace 与 timeline replay
  evals/                  # 确定性 Eval、FakeLLM runner 和文本报告
  core/                   # 配置和应用组装
  messaging/              # CLI、飞书和消息总线
  storage/                # 会话和记忆
  tools/                  # Agent 可调用的工具
workspace/
  instructions/           # AGENTS.md、SOUL.md、USER.md、TOOLS.md
  skills/                 # 本地 Skills
  memory/                 # 长期记忆
  sessions/               # 对话历史（JSONL）
evals/                    # 离线 EvalCase JSON 数据
```

`workspace/memory/` 和 `workspace/sessions/` 会随着运行产生数据。删除它们会丢失对应的记忆或会话历史，请先备份。

## Tracing 与离线 Evals

每次 Agent 请求都会在内存中生成独立 Trace，记录 Run、Agent Step、LLM 调用和
Tool 调用。Tool 参数及 metadata 中常见的 password、token、api_key、cookie、
secret 等字段会自动脱敏，Tool 输出预览最多保留 2000 字符。Trace summary 不会
进入 LLM 上下文。

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
Failure Recovery 和 Policy Guardrails。Replay 只读取已有 Trace 并输出 timeline，
不会再次调用模型或真实 Tool。

## Guardrails 与 Human-in-the-loop

每个模型提出的 Tool Call 都会先完成参数解析和浏览器 session 归一化，再进入
`ToolPolicy`。Policy 在 `ToolRegistry.execute()` 前给出独立的风险等级和执行决策：

```text
Proposed Tool Call
        ↓
    ToolPolicy
        ↓
ALLOW / REQUIRE_CONFIRMATION / BLOCK
        ↓
   ToolRegistry（仅 ALLOW 或已批准的 exact action）
```

- 自动执行：文件读取、页面读取与导航、普通点击、普通工作区文件写入、记忆写入，
  以及 `python --version`、`git status` 等高置信度只读 Shell 查询。
- 要求确认：`browser_eval`、长期记忆删除、敏感配置或 instruction 文件写入、删除/
  移动/安装/提交等会改变状态的 Shell 命令，以及快照中明确标记为删除、付款、发布、
  发送等高影响动作的浏览器点击。
- 直接阻止：高置信度识别到的系统级破坏命令，例如删除文件系统根目录、格式化磁盘、
  关机或重启。被阻止的调用不会进入 Tool Registry。

需要确认时，本轮 Run 以 `awaiting_confirmation` 结束，CLI 或飞书会显示 Tool、风险、
原因和 Approval ID。回复 `确认`、`继续`、`同意`、`执行`、`yes`、`y` 或 `approve`
会批准当前会话中那个确切的 Tool 和参数，并且只执行一次；回复 `取消`、`拒绝`、
`不要执行`、`停止`、`no`、`n` 或 `deny` 会取消它。其他回复会取消旧审批并作为新的
正常任务处理。审批仅保存在内存中、按 `channel:chat_id` 隔离，程序重启后不会恢复。

Policy 的 `risk_level`、`policy_decision`、`policy_rule`、`policy_reason`、`approval_id`
和 `approval_status` 会写入现有 Tool Call Trace，并继续使用相同的敏感字段脱敏。
Guardrails 是 Runtime Safety Layer 的第一版，不是完整 sandbox 或操作系统级安全边界；
它只做少量高置信度、确定性、可测试的判断。

## 浏览器工具

浏览器工具不是 Python 的 `playwright` 包，而是通过命令行调用 `playwright-cli`。常见工具包括：

- `browser_attach`：通过 CDP 连接已经打开并保留登录状态的本地 Chrome
- `browser_open`：启动 MyBot 管理的独立 Chrome，并复用持久化登录状态
- `browser_goto`：在已有 session 中跳转
- `browser_tab`：列出、新建、选择或关闭标签页
- `browser_snapshot`：读取当前页面
- `browser_links`：按页面视觉顺序列出并去重链接，适合选择第 N 个结果
- `browser_click`、`browser_type`、`browser_press`：操作页面
- `browser_eval`：执行页面 JavaScript
- `browser_close`：关闭 session

未明确指定时，Agent 默认调用 `browser_open` 并使用 `managed_browser`。只有消息
明确包含“本地浏览器”“当前 Chrome”“已打开的浏览器”等意图时，才调用
`browser_attach` 并使用 `local_browser`。每轮请求会锁定一种模式，不会因上一轮
的活动 session 而串用浏览器，也不会在一种模式失败后自动切换到另一种模式。

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

这是模型服务的限流或额度问题，不是本项目安装失败。检查 API 额度、模型名称和服务商限制；也可以适当降低请求频率或调整 `llm.rate_limit_retries`。

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
