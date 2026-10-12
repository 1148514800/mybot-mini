# AI Handoff

## 当前状态

项目已收敛为本地 CLI AI 助手，保留 OpenAI 兼容模型调用、ReAct 工具循环，以及工作区内文件读写。浏览器、MCP、Tracing 和 shell 执行已移除。

当前目标已完成：为 Agent 添加默认关闭的调试日志。设置 `MYBOT_DEBUG=1` 后输出每步模型耗时、token 数、工具调用数，以及工具参数和执行结果摘要；参数中的 `content` 仅显示字符数。修改文件：`mybot/agent/loop.py`、本交接文档；沿用现有工具循环，无架构变更。

## 核心结构

- `mybot/main.py`：程序入口
- `mybot/app.py`：应用组装和资源关闭
- `mybot/config.py`：读取配置并创建模型客户端
- `mybot/agent/`：提示词和 Agent 循环
- `mybot/tools/`：工具接口、注册表和文件读写
- `mybot/workspace.py`：初始化工作区说明文件

## 验证

- `.venv/bin/python -m compileall -q -x '/\._' mybot`：通过（排除磁盘元数据文件）。
- 虚拟环境内模拟模型/工具调用：默认关闭、非 `1` 值关闭、开启日志、正文隐藏、缺少 usage、非法 JSON 和执行参数保持原样均通过。
- `config/config.example.json` JSON 解析：通过。
- 模块导入与默认工具注册：通过；只注册 `read_file`、`write_file`。
- `git diff --check`：通过。
- CLI 启动未完成：本地没有 `config/config.json` 和 API Key，需复制模板并填写后验证真实模型调用。
- 系统 Python 缺少 `openai`；验证使用项目 `.venv`。工作区有既存 `mybot/app.py` 未提交修改，本任务未改动或提交该文件。

## 下一步

按需设置 `MYBOT_DEBUG=1` 验证真实模型调用；无需重复实现调试日志。
