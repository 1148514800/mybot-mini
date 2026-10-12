# AI Handoff

## 当前状态

项目已收敛为本地 CLI AI 助手，保留 OpenAI 兼容模型调用、ReAct 工具循环，以及工作区内文件读写。浏览器、MCP、Tracing 和 shell 执行已移除。

当前目标已完成：为 Agent 添加默认关闭的调试日志。配置文件顶层设置 `"debug": true` 并重启后输出每步模型耗时、token 数、工具调用数，以及工具参数和执行结果摘要；参数中的 `content` 仅显示字符数。修改文件：`mybot/config.py`、`mybot/agent/loop.py`、配置模板、README 和本交接文档；沿用现有工具循环，无架构变更。

## 核心结构

环境管理约定：使用 `uv` 管理依赖和运行环境；后续运行与验证优先使用 `uv run`，不要使用系统 Python。CLI 启动命令：`uv run python -m mybot.main`。调试日志仅由 `config/config.json` 顶层布尔字段 `debug` 控制，默认 `false`；不再读取 `MYBOT_DEBUG`。本地配置已补齐该字段，真实配置不提交。

- `mybot/main.py`：程序入口
- `mybot/app.py`：应用组装和资源关闭
- `mybot/config.py`：读取配置并创建模型客户端
- `mybot/agent/`：提示词和 Agent 循环
- `mybot/tools/`：工具接口、注册表和文件读写
- `mybot/workspace.py`：初始化工作区说明文件

## 验证

- `uv run python -m compileall -q -x '/\._' mybot`：通过（排除磁盘元数据文件）。
- 虚拟环境内模拟模型/工具调用：默认关闭、开启日志、正文隐藏、缺少 usage 和执行参数保持原样均通过；非法 JSON 日志处理沿用已验证实现。
- `config/config.example.json` JSON 解析：通过。
- 模块导入与默认工具注册：通过；只注册 `read_file`、`write_file`。
- `git diff --check`：通过。
- 真实模型调用未验证；本地存在 `config/config.json`，未输出凭证。
- `uv run` 配置及模拟日志验证通过：缺省关闭、布尔开关、环境变量不覆盖、正文隐藏、原始工具参数保持不变。
- 系统 Python 缺少 `openai`；验证使用 `uv run`。工作区有既存 `mybot/app.py` 未提交修改，本任务未改动或提交该文件。

## 下一步

按需将配置的 `debug` 设为 `true`，重启并验证真实模型调用；无需重复实现调试日志。
