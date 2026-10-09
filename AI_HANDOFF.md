# AI Handoff

## 当前状态

项目已收敛为本地 CLI AI 助手，保留 OpenAI 兼容模型调用、ReAct 工具循环，以及工作区内文件读写。浏览器、MCP、Tracing 和 shell 执行已移除。

## 核心结构

- `mybot/main.py`：程序入口
- `mybot/app.py`：应用组装和资源关闭
- `mybot/config.py`：读取配置并创建模型客户端
- `mybot/agent/`：提示词和 Agent 循环
- `mybot/tools/`：工具接口、注册表和文件读写
- `mybot/workspace.py`：初始化工作区说明文件

## 验证

- `python3 -m compileall -q mybot`：通过。
- `config/config.example.json` JSON 解析：通过。
- 模块导入与默认工具注册：通过；只注册 `read_file`、`write_file`。
- `git diff --check`：通过。
- CLI 启动未完成：本地没有 `config/config.json` 和 API Key，需复制模板并填写后验证真实模型调用。

## 下一步

无。
