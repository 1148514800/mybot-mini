# Phase 01：Agent Tool Calling 可观测化

archive-ready: true

## 1. 学习目标

理解一次用户输入如何经过模型、工具调用和模型总结形成回答，并通过日志观察每次模型请求和工具执行。能独立安装、运行和修改此版本。Phase 01 归档包含补齐的学习文档及归档脚本，不包含当前工作区尚未提交的 Phase 02 `list_files`。

## 2. Agent 核心概念

LLM 接收消息与工具的 JSON Schema，自行决定直接回答还是返回 `tool_calls`。Tool Calling 是模型提出调用请求，真正执行由本地 Python 完成。工具结果以 `role=tool` 和 `tool_call_id` 返回模型。这里使用有限循环实现“请求模型 → 执行工具 → 再请求模型”，不是无限自主执行，也不保存跨用户消息历史。

可观测化帮助区分模型耗时、调用了哪些工具、工具执行是否成功。tokens 为服务端返回的本次请求总量，不是工具执行成本；服务端未提供 usage 时显示 `?`。

## 3. 完整架构与流程

```text
main.py → run_gateway → GatewayConfig / init_workspace
                     → ToolRegistry + ContextBuilder + AgentLoop
用户输入 → handle_message → context.build_messages
         → 模型 API（携带工具 Schema）
         → 无 tool_calls：返回文本
         → 有 tool_calls：追加 assistant 消息
         → _execute → registry.execute → 文件工具
         → 追加 tool 消息 → 下一步模型 API
```

循环最多 `max_react_steps` 步，实际约束为 1–30。模型请求通过 `asyncio.wait_for` 超时控制。工具执行失败会返回 ToolResult 错误，模型可以据此调整下一步；耗尽步数则返回上限提示。CLI 遇到运行时错误显示提示，继续接受输入。退出时关闭模型客户端。

## 4. 核心文件职责

| 文件 | 职责 |
| --- | --- |
| `mybot/main.py` | CLI 入口与 asyncio 启动 |
| `mybot/app.py` | 组装配置、模型客户端、工具和 Agent，关闭资源 |
| `mybot/config.py` | 读取项目根目录 config/config.json，创建 OpenAI 兼容客户端 |
| `mybot/agent/context.py` | 拼接系统规则、工作区 instructions 和用户消息 |
| `mybot/agent/loop.py` | 请求模型、记录日志、执行 Tool Calling 循环 |
| `mybot/tools/base.py` | Tool 接口、Schema 转换与 ToolResult |
| `mybot/tools/registry.py` | 按名称注册工具、查 Schema、统一执行错误边界 |
| `mybot/tools/file.py` | 工作区路径校验、read_file 和 write_file |
| `mybot/workspace.py` | 初始化缺失的工作区说明文件 |
| `scripts/check_phase.py` | 不连接模型 API 的离线回归检查 |

## 5. 关键函数原理和调用关系

`GatewayConfig` 从 JSON 生成运行配置，`debug` 缺省为 false，仅 JSON 布尔 true 开启；不读取 MYBOT_DEBUG。配置在导入时加载，修改后需重启。

`ContextBuilder.build_messages` 为每次输入新建 system/user 消息，并读取 `workspace/instructions` 中 AGENTS、SOUL、USER、TOOLS 文档。

`AgentLoop.handle_message` 将工具定义传给 `chat.completions.create`。每步调用前记录 perf_counter，响应后输出 `[LLM N]` 的耗时、tokens、tool_calls 数。存在工具请求时，先保留模型的 assistant/tool_calls 消息，再顺序执行所有请求，最后追加各自的 tool 结果。

`AgentLoop._execute` 解析 JSON，验证参数是对象、工具存在、必填字段及字符串类型，再委托 `ToolRegistry.execute`。注册表捕获工具异常，并拒绝非 ToolResult 返回值。

文件工具共享 `_resolve`，解析相对路径、展开用户目录并 resolve，然后确保路径仍在 workspace 内。write_file 创建父目录并写 UTF-8；read_file 最多返回 50000 字符。这是本地路径保护，并非针对并发恶意修改的完整沙箱。

## 6. 新增和修改

Phase 01 在原有文件助手上增加 `[LLM]`、`[CALL]`、`[RESULT]` 日志。工具参数 content 被替换为字符数占位符，传给工具的原始 JSON 不变；结果仅输出长度、成功状态及 error，不打印结果正文。非法 JSON 日志显示 `<invalid JSON>`。

最初日志使用环境变量，之后已提交的配置变更将其统一为 JSON `debug`。本归档保存配置版本。其他参数及错误文本仍会显示，调试日志并非通用秘密脱敏器。

## 7. macOS + uv 安装、运行、测试

```bash
uv sync --frozen
cp config/config.example.json config/config.json
# 填入所选 provider 的 api_key、base_url、model
uv run python mybot/main.py
uv run python -m scripts.check_phase
uv run python -m compileall -q mybot
```

使用 macOS zsh、Python 3.12+ 和 uv。配置示例含默认关闭的 `"debug": false`，开启改为 true 并重启。输入 exit/quit 退出。配置和 workspace 路径基于项目根目录，真实配置不会进入 ZIP。

## 8. 实际测试案例与结果

本阶段已用独立目录与模拟模型验证：

| 案例 | 预期与实际结果 |
| --- | --- |
| debug=false | 无调试输出，通过 |
| debug=true，模拟 write_file 后模型回答 | 两步 LLM 日志、CALL/RESULT、tokens=42 与缺少 usage 的 ?，通过 |
| 写入 PRIVATE_BODY | 文件内容完整，日志只含 <12 chars>，通过 |
| 工具消息反馈 | 第二次请求携带 role=tool 消息，通过 |
| 非法 JSON、未知工具、工作区外路径 | 返回失败 ToolResult，通过 |
| 读取已写文件 | 返回原始文本，通过 |
| ZIP 独立安装和编译 | uv sync --frozen、compileall 和离线检查通过 |

真实模型 API 未验证，需要用户的有效凭证和服务可用性；上述模拟结果不代表线上模型成功。

## 9. 常见问题与注意事项

- 缺少 API Key：复制模板并填写，不要提交 config/config.json。
- 修改 debug 无效：确认配置中的布尔值而非字符串，重启进程。
- `tokens=?`：兼容服务未返回 usage，不属于工具错误。
- 工具耗时不包含在 LLM time 中；日志不记录工具耗时。
- 请求超时：检查网络、服务和 request_timeout_seconds。
- ExFAT 出现 `._*.py`：macOS 元数据；清理后编译，或在 APFS 目录运行。归档不包含这些文件。
- 同名 Tag/ZIP/学习目录存在：不要覆盖，核对版本；学习目录可自行另存，脚本默认固定独立目录。

## 10. 与上一阶段的变化及版本事实

上一基线为 `7ccc223` 的核心文件助手，已有 read_file、write_file、上下文和工具循环。日志由 `e6cd1c2` 引入，配置控制由 `11d369e` 引入。本次仅补齐归档设施和学习资料，并验证已提交 Phase 01 实现，不重写历史。

Phase 02 的 list_files、注册变更和提示词变更仍未提交，不包含在 phase-01 Tag 中。phase-01 指向本次带学习文档的归档提交，后续历史通过 Git 查阅。
