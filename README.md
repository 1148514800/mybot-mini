# MyBot

MyBot 是一个简洁的本地命令行 AI 助手，通过 OpenAI 兼容接口调用模型，并可在指定工作区中读取和写入文件。

## 需要的软件

- Python 3.12 或更高版本
- OpenAI 或兼容服务的 API Key

## 安装与配置

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp config/config.example.json config/config.json
```

编辑 `config/config.json`，填写提供商的 `api_key`、`base_url` 和 `model`。真实配置文件不会提交到 Git。

Windows PowerShell 可使用：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
Copy-Item config\config.example.json config\config.json
```

## 启动

```bash
python mybot/main.py
```

输入问题并按 Enter 开始对话，输入 `exit` 或 `quit` 退出。每条消息独立处理，不保存历史对话。Agent 可以调用 `read_file` 和 `write_file`，文件操作限制在配置的 `workspace.path` 目录内。

## 配置

```json
{
  "llm": {
    "provider": "siliconflow",
    "max_completion_tokens": 2000,
    "request_timeout_seconds": 60,
    "max_react_steps": 10,
    "providers": {
      "siliconflow": {
        "api_key": "YOUR_API_KEY",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "Qwen/Qwen3-235B-A22B-Instruct-2507"
      }
    }
  },
  "workspace": {"path": "./workspace"}
}
```

环境变量 `OPENAI_API_KEY`、`OPENAI_BASE_URL` 和 `MYBOT_MODEL` 可用于覆盖对应配置值。
