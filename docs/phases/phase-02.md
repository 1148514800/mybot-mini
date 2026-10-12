# Phase 02：自定义 Agent 工具 list_files

archive-ready: true

## 1. 本阶段学习目标

学会在已有 Agent 中增加一个工具：定义模型可见的 Schema、复用工作区路径边界、统一注册、将结果反馈给模型。能够独立还原本版本，用 list_files 浏览目录后继续读取文件，而不需要用户预先提供完整文件名。

## 2. Agent 核心概念

工具由名称、描述、参数 Schema 和执行函数组成。模型只提出调用意图，本地 Agent 解析参数并执行 Python。Schema 中的 path 是必填字符串，目录根使用 `.`。ToolResult 分离成功状态、文本输出、错误和 metadata，使模型可以基于实际结果回答。

工具注册决定模型能看到的能力。继承 FileTool 复用现有边界检查，避免为新工具创建第二套路径安全逻辑。list_files 是目录发现工具，read_file 读取内容，write_file 写入内容。

## 3. 当前阶段完整架构和执行流程

```text
main.py → app.run_gateway
        → GatewayConfig / init_workspace / OpenAI 客户端
        → build_default_tool_registry：read_file + write_file + list_files
用户输入 → ContextBuilder.build_messages → AgentLoop.handle_message
        → 模型返回 list_files(path)
        → AgentLoop._execute → ToolRegistry.execute
        → ListFilesTool.execute → FileTool._resolve → iterdir / 排序 / 格式化
        → ToolResult.to_text → role=tool 消息 → 模型再次请求 → 最终回答
```

保留 Phase 01 的有限 Tool Calling 循环、超时控制、文件读写、独立消息上下文和 debug 日志。list_files 是非递归操作，只列当前目录第一层，不读取文件正文。

## 4. 核心代码文件及职责

| 文件 | 职责 |
| --- | --- |
| mybot/main.py | asyncio CLI 入口 |
| mybot/app.py | 组装配置、客户端、上下文与工具，关闭资源 |
| mybot/config.py | JSON 配置、模型客户端、debug 开关 |
| mybot/workspace.py | 初始化 workspace/instructions |
| mybot/agent/context.py | 系统规则与用户输入，不再把能力限定为两个工具 |
| mybot/agent/loop.py | 模型请求、参数校验、工具执行与日志 |
| mybot/tools/base.py | Tool 接口、Schema、ToolResult |
| mybot/tools/file.py | 共享路径边界与文件读写 |
| mybot/tools/list_files.py | 本阶段新增的目录列表工具 |
| mybot/tools/registry.py | 统一注册并暴露三个工具 |
| scripts/check_list_files.py | 本阶段离线工具及模型循环验证 |
| scripts/check_phase.py | 通用回归，并在存在 list_files 时执行阶段专用验证 |

## 5. 关键函数原理和调用关系

`ListFilesTool.name/description/parameters` 实现 Tool 接口。`Tool.to_schema` 包装为 OpenAI function definition，注册表 `get_definitions` 将全部工具传给模型。Schema 声明 path 必填、类型 string 和 additionalProperties=false。

`ListFilesTool.execute(path)` 首先调用继承的 `_resolve`：展开用户目录，将相对路径连接到 workspace，resolve 符号链接后检查是否仍在工作区。越界返回失败 ToolResult；不存在或不是目录时返回 `not a directory`。

目录通过 `target.iterdir()` 获取第一层条目，以 `name.lower()` 排序。最多输出前 100 条，按 is_dir 分类为 `[DIR] 名称` 或 `[FILE] 名称`。无条目时输出 `(empty directory)`；metadata 的 total 是总条目数，shown 是实际显示数。异常统一转为失败 ToolResult。

`AgentLoop._execute` 在调用前验证 JSON 对象、必填字段、字符串类型。`ToolRegistry.execute` 根据名称调用工具，捕获异常。`ToolResult.to_text` 将输出和 metadata 传回模型，因此模型可以发现目录内容被截断。

## 6. 本阶段新增或修改功能

新增 ListFilesTool；在默认注册表中加入 list_files；系统规则改为使用“提供的工具”，适配动态工具集合。补充持久化离线测试，并让归档验证自动包含 list_files 测试。没有改变 Agent 循环、模型配置、历史保存方式或现有文件工具。

## 7. macOS + uv 安装、运行与测试

```bash
bash scripts/restore_phase.sh 2
cd ../mybot-mini-learning/phase-02
uv sync --frozen
cp config/config.example.json config/config.json
# 填写所选 provider 的 api_key、base_url、model
uv run python mybot/main.py
```

环境为 macOS/zsh、Python 3.12+、uv。在 config/config.json 顶层设置 `"debug": true` 并重启，可查看 CALL/RESULT 日志。尝试输入“列出工作区文件”或“列出 instructions 目录”。输入 exit/quit 退出。

```bash
uv run python -m scripts.check_list_files
uv run python -m scripts.check_phase
uv run python -m compileall -q mybot
```

开发目录若存在 ExFAT 的 AppleDouble 文件，编译可排除元数据：`uv run python -m compileall -q -x '/\._' mybot scripts`。归档使用 APFS 临时目录执行完整编译。

## 8. 实际测试案例及结果

| 测试 | 实际验证结果 |
| --- | --- |
| 注册与 Schema | 三个工具均注册，path 为必填字符串，通过 |
| 文件与目录列表 | `[FILE] alpha.txt`、`[DIR] Beta` 等分类正确，忽略大小写排序，通过 |
| 空目录 | 输出 empty directory，total/shown 均为 0，通过 |
| 105 个文件 | 仅显示 100 个，total=105、shown=100，最后条目为 099.txt，通过 |
| 不存在路径、普通文件 | 返回失败 ToolResult，通过 |
| 相对越界、绝对越界、指向外部的目录链接 | 拒绝执行，通过 |
| 工作区内部的绝对路径、目录链接 | 可列出，通过 |
| 缺失 path、数字 path、非法 JSON、数组参数 | Agent 参数检查拒绝，通过 |
| 模拟模型调用 list_files 后总结 | 两次模型请求，tool_call_id 正确、空目录结果反馈和 debug 日志正确，通过 |
| Phase 01 文件读写及日志回归 | 通过 |

独立归档验证执行 uv sync --frozen、compileall 和包含上述案例的通用离线检查。真实模型 API 未验证，模拟调用不代表线上模型一定会选择此工具。

## 9. 常见问题与注意事项

- path 使用 `.` 表示根目录，工具不会递归列出子目录。
- “not a directory” 同时覆盖不存在路径和普通文件路径，先检查输入。
- total 大于 shown 时列表被截断；当前没有分页能力，不应把这 100 条当作完整结果。
- 隐藏文件不会被过滤，AppleDouble 文件也可能作为目录条目出现；归档本身不包含它们。
- 列表中的链接按目标是否为目录分类，外部链接名称可以被显示，但单独列出该外部链接会被 `_resolve` 拒绝；不会遍历外部目录内容。
- 同名忽略大小写的条目排序依赖原始迭代顺序，不保证并列条目的固定先后。
- Schema 声明不接受额外字段，但本地通用执行器目前只检查必填字段与字符串类型，execute 的 kwargs 会忽略额外字段。这不是严格的完整 JSON Schema 校验。
- 100 条限制只限制返回量，仍会扫描并排序整个目录；很大的目录可能较慢。
- 文件系统可能在列出过程中变化，现有路径检查不构成对恶意并发修改的完整沙箱。
- config/config.json 含真实凭证，不提交，不进入快照。修改 debug 需重启。

## 10. 与 Phase 01 的变化

Phase 01 只有 read_file 和 write_file，模型需要已知路径才能读取。Phase 02 新增目录发现能力，模型可以先列目录再读取目标文件。原有可观测化和配置开关保留。Phase 01 Tag 与 ZIP 不变，本阶段拥有独立 phase-02 Tag 和源码快照；原有 app.py 注释修改未纳入本阶段提交。
