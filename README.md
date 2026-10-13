# MyBot

MyBot 是一个简洁的本地命令行 AI 助手，通过 OpenAI 兼容接口调用模型，并可在指定工作区中读取和写入文件。

## 需要的软件

- Python 3.12 或更高版本
- OpenAI 或兼容服务的 API Key

## 安装与配置

```bash
uv sync
cp config/config.example.json config/config.json
```

编辑 `config/config.json`，填写提供商的 `api_key`、`base_url` 和 `model`。真实配置文件不会提交到 Git。

Windows PowerShell 可使用：

```powershell
uv sync
Copy-Item config\config.example.json config\config.json
```

## 启动

```bash
uv run python -m mybot.main
```

输入问题并按 Enter 开始对话，输入 `exit` 或 `quit` 退出，输入 `/clear` 清空当前会话。进程内默认保留最近 6 个完整用户轮次（含工具请求和结果），默认退出后不保存历史；开启 session.persist 后可跨重启恢复。Agent 可以调用 `read_file` 和 `write_file`，文件操作限制在配置的 `workspace.path` 目录内。

## 配置

```json
{
  "debug": false,
  "session": {"max_turns": 6, "persist": false, "path": "./.mybot_state/session.json"},
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

将 `config/config.json` 顶层的 `debug` 设置为 `true` 开启调试日志，设置为 `false` 关闭，默认关闭。修改后重启程序生效。日志包含模型耗时、token 数、工具参数及执行结果摘要；写入参数 `content` 仅显示字符数。调试开关统一由配置文件控制，不再读取 `MYBOT_DEBUG` 环境变量。


## Phase 学习归档

学习索引与独立运行方法见 [docs/phases/README.md](docs/phases/README.md)。完成阶段、验证并提交相关文件后，在干净工作区执行：

```bash
bash scripts/save_phase.sh 2 "自定义 Agent 工具 list_files"
bash scripts/restore_phase.sh 1
```

保存会创建唯一 Tag 并将完整源码 ZIP 写到 `../mybot-mini-snapshots/`；还原到 `../mybot-mini-learning/phase-01`，不修改开发分支，拒绝覆盖已有版本。Phase 01–05 已分别归档；已存在的 Tag 和 ZIP 不可重复保存。

归档设施验证命令：`uv run python -m scripts.test_phase_archives`。

对话历史轮数通过 `config/config.json` 的 `session.max_turns` 调整，默认 `6`，必须是正整数。修改后重启生效；这是保留历史的轮数，不是单次任务工具循环的 `llm.max_react_steps`。

复杂多步任务可由模型调用 `create_plan` 建立 2–6 步计划，并通过 `update_plan` 显示执行进度；简单任务直接执行，不增加独立分类请求。步骤完成需要实际工具成功结果；失败或未验证会明确报告。每条用户任务重新开始计划，`/clear` 同时清空历史和计划。详见 [Phase 04](docs/phases/phase-04.md)。

Session 持久化默认关闭。配置 `session.persist=true` 并重启后，完整历史轮次保存到 `session.path`（默认项目根 `.mybot_state/session.json`，必须在 workspace 外）。`/clear` 同时清空磁盘历史；JSON 损坏会报错并保留原文件。恢复不会重放旧工具或恢复 Plan 状态。详见 [Phase 05](docs/phases/phase-05.md)。自定义状态目录也应加入 `.gitignore`；ExFAT 无法保证 POSIX 私有权限，聊天历史以明文保存。
