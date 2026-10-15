# Phase 10：MCP Client 与本地外部工具

archive-ready: true

## 1. 学习目标与 MCP 概念

本阶段学习让同一个 Agent 通过标准协议使用外部程序提供的工具，涵盖握手、发现、参数 Schema、调用、错误和进程生命周期。只实现用户配置的可信本地 stdio MCP Tools，不增加远程安装、HTTP/SSE、Resources、Prompts、采样、重连或新的 Agent 循环。

参考 [MCP 2025-11-25 规范](https://modelcontextprotocol.io/specification/2025-11-25)、[官方 Python SDK](https://github.com/modelcontextprotocol/python-sdk) 和 [2.x Client 文档](https://py.sdk.modelcontextprotocol.io/client/)。本地通过 uv 安装并实际测试 mcp 2.3.0、mcp-types 2.3.0，使用 2.x 的 Client、MCPServer、snake_case 字段；没有混用 1.x FastMCP/ClientSession 示例。

MCP Host 是 mybot 应用，负责模型、工具权限和连接；Client 负责一条与 Server 的协议连接；Server 是提供工具的独立程序。Tool 是实际能力接口，Skill 是如何使用能力的指导文本，MCP 是发现/调用外部能力的协议。加载 Skill 不等于启动 Server；Agent 不能自行生成启动配置。

## 2. 当前完整架构与执行流程

```text
GatewayConfig → run_gateway
  → 原生 ToolRegistry
  → async with MCPClientManager
      → SDK stdio_client 启动可信子进程（固定项目根 cwd，stderr独立）
      → Client(mode=legacy) → initialize / notifications/initialized
      → tools/list（支持分页，数量受限）→ allowed_tools 过滤
      → MCPToolAdapter 校验名称/Schema → 全部通过后注册
  → 原 AgentLoop → Function Calling → ToolRegistry → MCPToolAdapter
  → JSON Schema校验 → Client.tools/call → Server → ToolResult
  → 原 ReAct / Planning / Session / ContextManager
  → Agent退出/异常/取消 → SDK关闭连接、子进程 → LLM Client关闭
```

stdio 使用子进程 stdin/stdout 上按行传输的 JSON-RPC 消息。序列化、请求ID关联、通知、握手、超时、传输和进程停止全部由官方 SDK 负责，没有手写 JSON-RPC。Server stdout 专用于协议，stderr 通过独立文件句柄送到 devnull，避免凭证或非协议日志泄露到CLI。

Client 选择 mode=legacy，以本阶段规范的 initialize 握手协商；与真实 Demo 的实测 protocol_version 是2025-11-25。没有采用 SDK auto 的新协议发现路径，也不把 Server.instructions 加入 System Prompt。工具描述只出现在普通 Function Calling 定义中，结果以普通 Tool 消息返回，不提升为系统规则。

## 3. 核心源码与职责

| 文件 | 职责 |
| --- | --- |
| mybot/mcp_client/config.py | 纯配置校验与深复制，不启动进程 |
| mybot/mcp_client/manager.py | stdio连接、握手、分页发现、原子注册、call与退出 |
| mybot/mcp_client/adapter.py | Tool接口、命名、Schema子集校验、参数验证、结果转换 |
| mybot/app.py | 在网关异步生命周期中持有Manager |
| mybot/config.py | mcp_enabled / mcp_servers 配置默认值与校验 |
| mybot/agent/loop.py | 只增加MCP调试参数遮蔽，执行循环/协议不变 |
| scripts/mcp_demo_server.py | 官方MCPServer提供add/echo，无文件/网络/Shell操作 |
| scripts/check_mcp.py | 真实子进程+官方协议+模拟LLM的17项专项测试 |

ToolRegistry.register 原有行为不变。Manager 在注册前检查所有映射是否冲突；不依赖 register 自动覆盖。没有重写 AgentLoop、Planning 或 Session。

## 4. 配置、权限与启动边界

```json
"mcp": {
  "enabled": false,
  "servers": {
    "demo": {
      "command": "uv",
      "args": ["run", "python", "-m", "scripts.mcp_demo_server"],
      "allowed_tools": ["add", "echo"],
      "timeout_seconds": 10
    }
  }
}
```

默认关闭，只有用户显式设置 true 才执行配置命令。配置模板和本地配置补齐开关，但本地实际配置不提交。command 是一个可执行程序名或路径，args 是单独的字符串数组，不使用 shell=True，不拼接模型文本，不自动安装 Server。工作目录始终为项目根，不随调用CLI的当前目录变化。

服务器最多8个，名称1–20字符，首字母为小写英文字母，后续小写字母/数字或单连字符，避免命名空间歧义。args最多64项、单项最多8192字符；command非空且最多4096字符，均拒绝NUL。allowed_tools必须明确列出、唯一、最多64项；缺少allowlist不会默认全部允许。timeout为有限数值(0,120]秒，拒绝bool。字段类型、未知字段与非法名称明确报错。

本地 ReadFileTool/WriteFileTool 的 workspace路径约束只保护内置文件工具。MCP Server 是以用户权限运行的本地程序，不受该约束自动保护；allowlist是功能授权，不是操作系统沙箱。不根据readOnly/destructive声明自动放行，示例仅验证无副作用工具。不要把包含凭证的任意程序当成可信Server；未来有外部写入副作用的工具需要另行设计确认机制。

SDK传输只继承其有限默认环境（HOME/PATH等），本阶段不提供任意env配置或传入模型API Key。Server stderr被抑制，排查启动问题优先确认可信命令、依赖与允许工具；不能将完整stderr或参数放入调试日志。

## 5. Manager 生命周期、发现和失败收尾

__aenter__ 顺序连接服务器，并把SDK Client和传输句柄放进AsyncExitStack。SDK负责连接与初始化，read_timeout_seconds限制握手/读取等待；tools/list逐页发现，最多256条/Server，重复游标或超过16个后续游标拒绝。只为allowlist中的定义创建适配器；允许名单里有未发现的工具也明确拒绝。

所有服务器/定义验证完成后才按名称排序注册。某个Server失败会先关闭已连接Server并抛MCPStartupError，没有半注册工具，也不改原生注册项。网关此时不启动CLI，修正配置后重启；不会静默假装外部工具可用。错误只显示受控服务器名、阶段和安全类别，如executable_not_found、timeout或固定Schema错误，不转发外部异常全文。

SDK内部持有AnyIO上下文，因此enter/exit和MCP调用必须在同一个网关Task。没有用asyncio.wait_for包住Client.__aenter__，避免把连接建立与清理分配给不同任务。普通工具调用用SDK自身read timeout；成功工具返回后连接复用。跨Task调用被安全拒绝，本阶段不支持并发使用同一Manager。

远端isError是一次正常协议响应，不关闭连接，但转换为失败ToolResult。协议异常、工具超时或断连则在owner Task关闭整个Manager的MCP连接和子进程，后续MCP调用明确不可用，需重启网关；原生工具仍在。退出、异常、取消同样释放所有资源。__aexit__使用aclose清理而不把业务异常注入SDK任务组，避免业务异常被包装成不易辨识的ExceptionGroup。

## 6. 工具名称、Schema与调用原理

原名add映射为mcp__demo__add，不同Server即使同名也不冲突；实际调用仍使用远端原名add。远端名只接受ASCII字母/数字/下划线/连字符，映射总长最多64，不做可能歧义的替换。点号、过长名和已有映射冲突明确拒绝。不能覆盖read_file、create_plan等原生能力。

input_schema深复制保留type、required、enum、数组、嵌套对象及边界约束，用Draft202012Validator.check_schema验证，再限制为保守的非strict Function Calling子集。支持properties、items、additionalProperties、anyOf、数值/长度/数量边界等；拒绝$ref/$defs、oneOf、pattern等未测试结构，不下载远程Schema、不悄悄删除约束。Schema最多32768字符、递归深度12，description最多4096字符。

Adapter.execute 用同一Schema验证完整JSON参数，并拒绝NaN等非标准JSON。即使LLM绕过Schema给出错误enum、字符串冒充number、bool冒充number、数组元素或嵌套类型错误，也返回失败，错误不含原始参数。验证后manager.call向SDK转发原名与原始JSON对象。第三方Provider具体支持程度还需单独验证；本阶段只对该保守子集做本地协议/模拟LLM测试，不声称所有Provider兼容。

## 7. ToolResult、Planning、Session与Context

多个文本块按顺序合并；structured_content用安全JSON序列化附加到文本中。is_error=true始终success=false，远端错误正文可能含敏感参数，因此只给通用错误标记。图片/音频/二进制/资源块、非完整多轮结果或无法安全序列化的结构化内容明确失败，不丢掉部分内容后声称处理成功。

适配器输出最多12000字符，超出附明确MCP截断标记与metadata.truncated=true。这是传入Agent的结果上限，SDK接收原始协议数据时不提供本项目自定义的字节级内存沙箱。ContextManager之后还可裁剪请求副本；Session保存适配器已限长的原始ToolResult与原始调用参数，不保存超出适配器上限的远端全文。

MCP工具遵循原AgentLoop普通工具路径：成功结果可为活动Plan步骤提供执行证据，失败则由Plan.observe记录失败，不凭模型自称成功。截断标记说明部分内容未处理，不能据此宣称完整分析。Schema和返回内容一起计入Context预算；Skills的正文保护策略不变。

Tool Call ID由原循环写入assistant.tool_calls和tool.tool_call_id，真实MCP请求ID由SDK独立管理，两者不混淆。/clear仅清空Session/磁盘历史与Plan，不关闭或重启MCP；恢复旧Session不会重放工具。MCP默认关闭时原有工具和CLI行为不变。调试输出仅MCP工具名、参数遮蔽、结果长度和安全错误，不打印完整MCP参数或正文。

## 8. macOS + uv 安装、运行与验证

```bash
uv sync --frozen
test -e config/config.json || cp config/config.example.json config/config.json
# 已有真实配置不要覆盖：只编辑mcp.enabled=true，保留已有LLM字段
uv run python mybot/main.py
```

手工任务示例：“调用mcp__demo__add计算2.5加4，再调用mcp__demo__echo返回hello”。真实LLM调用需要本地密钥，但本次开发/归档没有调用真实模型API。Demo MCP协议测试不需要Key。

```bash
uv run python -m scripts.check_mcp
uv run python -m scripts.check_phase
uv run python -m scripts.test_phase_archives
uv run python -m compileall -q -x '/\._' mybot scripts
```

Demo可以用uv run python -m scripts.mcp_demo_server直接启动，但stdout是协议，不是交互命令行，等待连接是正常状态。通过配置启动时由Manager负责终止。依赖锁定mcp/mcp-types2.3.0和jsonschema4.26.0；jsonschema作为直接依赖用于完整参数验证，避免手写类型判断；官方SDK的传递依赖仍会安装，即使只使用stdio。

## 9. 实际测试案例与结果

17项专项测试通过，使用真实Demo/临时SDK测试Server与模拟LLM，不以假MCP Client冒充协议通信：

- 默认关闭不启动；配置错误拒绝。
- 真实stdio握手2025-11-25、tools/list发现、allowlist过滤、add=6.5与echo正确；模板uv命令与固定cwd实际启动。
- 两Server同名区分、不覆盖原生read_file、映射冲突拒绝且原子清理。
- number/bool区别、enum/数组/嵌套对象验证；不支持Schema与非法/过长名称拒绝。
- 多文本、结构化返回、图片拒绝、长结果显式截断、isError不泄露远端正文。
- 命令不存在、错误Schema、缺失allowed工具、握手超时、工具超时、服务中途退出均失败并释放进程。
- 正常退出、业务异常、初始化期间取消及连接后取消，PID消失；跨Task调用拒绝。
- 真MCP工具经模拟LLM调用，消息ID配对、Session记录和/clear正确；Gateway退出/异常也关闭MCP和LLM Client。
- Planning成功/失败证据正确，Skills可混合调用；长MCP结果请求副本裁剪，Session保留适配器原始限长结果；Schema预算计量有效；debug参数遮蔽。

Phase1–9已有Agent回归及40项Evaluation/诊断测试执行通过。归档安全检查与独立ZIP冻结安装、编译、全部回归在APFS临时目录验证。app.py用户三处注释与USER.md修改保留，不进入Phase10提交；诊断补充已在独立ac9f823提交，不移动phase-09。

## 10. 相比Phase9的变化、常见问题与局限

Phase9是评测能力，本阶段添加一个受配置控制的本地协议入口和两个演示工具，仍然只有原有Agent循环。外部能力可复用ToolRegistry/Planning/Session/Context，而无需成为新的内置工具类或Skill执行器。

启动失败先看安全阶段/类别，检查uv是否在PATH、项目依赖是否冻结安装、allowlist名称是否真实存在。发现工具但Schema不支持时拒绝启动，不静默降级。模型请求可能因Schema总量超过Context预算而失败，减少允许工具或调整预算；字符不等于Token。工具失败后连接已关闭时要重启网关，/clear不会重新连接。

只支持可信本地stdio、串行owner Task与文本/JSON；无自动重连、远端地址、任意env、Server动态更新通知、MCP授权平台或多轮工具输入支持。stderr为隐私而抑制，诊断细节有限。进程以用户权限运行，无OS沙箱；当前仅无副作用Demo通过验证，真实第三方Server和有外部写入的工具需要后续单独设计权限与确认。

不修改Phase1–9 Tag/ZIP，不包含密钥/真实Session/留存报告，不自动Push，不进入Phase11。ExFAT可能仍由macOS生成AppleDouble，归档排除._*，复制设置COPYFILE_DISABLE=1，独立验证优先APFS。
