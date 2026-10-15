# Phase 12：MCP Streamable HTTP 与多传输管理

## 1. 学习目标与概念

本阶段在 Phase 10 的 stdio 和 Phase 11 的调用审批之上增加 Streamable HTTP。学习传输与工具语义分离、HTTP 会话生命周期、网络授权边界，以及网络故障中的不确定性。不引入新的 Agent 框架，不改 AgentLoop，不进入 Phase 13。

mybot 是 **Host**：管理模型、工具、权限和用户交互。每个配置的 Server 对应一个 SDK **Client** 协议连接；**Server** 提供工具，可能是子进程，也可能是独立的 HTTP 服务。模型看到的是 mcp__server__tool 的统一 Function Calling 接口，不需要知道连接使用哪个 transport。

参考 [2025-11-25 Transport 规范](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)、[官方 Python Client 文档](https://py.sdk.modelcontextprotocol.io/client/)、[Transport 文档](https://py.sdk.modelcontextprotocol.io/client/transports/)及 [Python SDK](https://github.com/modelcontextprotocol/python-sdk)。实际以本地锁定的 **mcp/mcp-types 2.3.0** 为准，没有混用 1.x ClientSession/FastMCP 示例，也没有升级 SDK。

## 2. stdio 与 Streamable HTTP

| 项目 | stdio | Streamable HTTP |
| --- | --- | --- |
| 承载方式 | stdin/stdout 上的 JSON-RPC | 单一 /mcp Endpoint 上的 HTTP |
| Server 生命周期 | Manager 启动并清理子进程 | 用户独立启动，Manager 不终止其进程 |
| 连接配置 | command、args | url |
| 主要风险 | 启动的程序拥有本地用户权限 | 网络目标、代理、重定向、数据发送、远端状态不确定 |
| 共享部分 | ToolRegistry、Adapter、Schema、审批、Plan、Session、Context | 同左 |

每个客户端 JSON-RPC 消息通过一次 HTTP POST 发送。Server 可以返回 application/json，也可以在 POST 响应中通过 SSE（text/event-stream）逐个发送消息。客户端可以额外 GET 同一 Endpoint 建立接收 Server 通知的 SSE 流；GET 是可选的，Server 可以返回 405。SSE 是响应编码和流式传递方式，不是另一套 Agent 执行逻辑。

Streamable HTTP 替代旧版 HTTP+SSE transport。旧传输通过 GET /sse 获得另一个 POST 地址；本阶段不做该旧协议回退，也不根据 Server 消息动态接受新地址。JSON-RPC 编解码、ID、SSE、握手及 MCP 会话 Header 全部由官方 SDK 实现。

## 3. HTTP Session 与进程内笔记

初始化仍是 mode="legacy" 下的 initialize → notifications/initialized，Demo 实测协商版本 2025-11-25。Server 在有状态模式下返回 Mcp-Session-Id；SDK 在后续请求中携带它，退出连接时发送 DELETE /mcp 终止协议会话。DELETE 结束的是 MCP Session，不是 HTTP Server 进程，也不会清空 Demo 的进程内笔记。

这里有三类不同状态：Agent Session 是给模型提供的对话历史；MCP Session 是协议连接状态；Demo notes 是 Server 进程中的共享字典。HTTP Client 退出后独立 Server 还在，笔记也还在，新 MCP Session 可以读到；重启 HTTP Server 才会清空。不同 stdio/HTTP 进程不共享字典。没有数据库、长期记忆或跨重启笔记保存。

默认 Demo 采用 **stateful_http（stateless_http=False）+ json_response=True**，便于检查 Session 建立与 DELETE。测试还真正运行 json_response=False 的 SSE 响应及 stateless_http=True 的 JSON 模式；后者没有 Mcp-Session-Id，退出不会发送 DELETE。

## 4. 配置与 macOS + uv 使用

旧配置不写 transport 时仍默认为 stdio。stdio 继续使用 command 和字符串列表 args；为保持 Phase 10/11 兼容，原先允许的 args 缺省 [] 仍有效。HTTP 配置只接受 url，不接受 command、args、headers、auth、proxy 等字段。allowed_tools、tool_policies、timeout_seconds 的校验保持不变。

以下是一个仅 HTTP 的配置片段，合并进已有 config/config.json，保留 llm、workspace 等字段：

```json
{
  "mcp": {
    "enabled": true,
    "servers": {
      "demo-http": {
        "transport": "streamable_http",
        "url": "http://127.0.0.1:8765/mcp",
        "allowed_tools": ["add", "echo", "save_note", "read_note", "delete_note"],
        "tool_policies": {
          "add": "allow", "echo": "allow", "read_note": "allow",
          "save_note": "confirm", "delete_note": "confirm"
        },
        "timeout_seconds": 10
      }
    }
  }
}
```

config/config.example.json 同时提供 demo（stdio）与 demo-http，整体 mcp.enabled 仍为 false。**启用时会连接所有配置的 Server**；只使用一种传输时，从自己的配置中移除另一项，而不是期待它按模型选择才启动。不修改已有真实配置，不把 API Key 放进 MCP URL。

```bash
uv sync --frozen
# 终端 A，独立 HTTP Server，仅绑定 127.0.0.1：
uv run python -m scripts.mcp_http_demo_server --port 8765
# 终端 B，配置中启用对应 Server 后：
uv run python mybot/main.py
```

例如请求 add，再请求保存 key=demo、content=hello。save_note 每次需要输入小写 yes；其他输入拒绝。read_note 可读取保存结果，delete_note 同样需要再次确认。退出 mybot 不会关闭终端 A 的服务，Server 用 Ctrl-C 停止。此人工模型流程本阶段没有实际执行，不能当作已验证的真实 LLM 能力。

## 5. 网络目标与安全边界

validate_http_url 只接受本地明确配置的目标：

- HTTP 必须是 ipaddress 能确认的字面量 loopback IP，例如 127.0.0.1、[::1]；不接受 localhost、127.1、整数形式地址或公网/内网非回环地址，避免主机名解析歧义。
- HTTPS 的信任由用户在本地 servers 配置中显式指定 URL 表达，验证证书，绝不自动接受模型、Skill 或 Tool Result 给出的新连接地址。没有新增认证能力。
- 拒绝用户名、密码、query（含空 ?）、fragment（含空 #）、反斜杠、控制字符、不合法端口或不安全 hostname。
- HTTP 客户端 trust_env=False、auth=None、retries=0；不继承 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY、netrc 或环境 CA 配置。发送前去掉 Authorization、Proxy-Authorization、Cookie，Server 不能靠 Set-Cookie 使后续请求隐式带身份信息。
- HTTPBoundary 在 request hook 检查完整 Endpoint，在 response hook 拒绝全部 3xx。比仅禁止跨 Origin 更保守：同 Origin 跳转也拒绝。SDK 自己可能处理 redirect，所以不能只设置 httpx2.follow_redirects=False。
- 禁止网络 GET 重连/resumption：允许首次可选 GET，之后的 GET 或 Last-Event-ID 请求在网络发送前拒绝。SDK 内部可能尝试重连，但不能产生第二次 GET 网络请求；不重发 tools/call POST，不重新 initialize，不自动恢复连接。

Origin 是 scheme + host + port。TLS 保护传输和证书校验，不证明 Server 可信。DNS rebinding 是将看似外部网站的名字解析到本机服务；Demo 固定绑定 127.0.0.1，并用官方 TransportSecuritySettings 精确限制 Host=127.0.0.1:实际端口、Origin=http://127.0.0.1:实际端口。错误 Host 返回 421，错误 Origin 返回 403；非浏览器调用可以没有 Origin。

这些限制不是 OS 沙箱，不保证远端不会存储已发送的数据。服务器 instructions 不提升到 System Prompt；描述保留在普通工具 Schema，正文只进入普通 Tool Result。HTTP 401/403 会失败，不自动打开 OAuth，也不添加 Bearer Token。需要认证的实际远程服务未获兼容性验证。

## 6. 核心模块与函数

| 文件 | 职责 |
| --- | --- |
| mybot/mcp_client/config.py | transport 与字段匹配、URL、安全目标校验，沿用权限与 timeout 校验 |
| mybot/mcp_client/transport.py | connect_transport、HTTPBoundary、安全 HTTP Client、协议日志抑制 |
| mybot/mcp_client/manager.py | 使用工厂选择连接，共用发现/注册/调用；安全异常分类及 owner Task 清理 |
| mybot/mcp_client/adapter.py | 未修改，沿用 JSON Schema、ToolResult、文本/JSON结果与12000字符上限 |
| mybot/mcp_client/approval.py | 未修改，沿用一次性批准与冻结 ApprovalRequest |
| scripts/mcp_http_demo_server.py | 独立官方 SDK HTTP app；复用 stdio Demo 的全部五个工具 |
| scripts/check_mcp_http.py | 真实 HTTP 子进程、真实 SDK Client、故障注入与模拟 LLM |
| config/config.example.json、pyproject.toml、uv.lock | 示例双传输，显式声明已安装的 httpx2/uvicorn 直接依赖 |
| scripts/check_mcp.py、scripts/check_phase.py | 调整传输探针位置、集成 Phase 12 回归 |

uv.lock 依然是原来的 41 个包，仅增加项目对已有 httpx2 2.13.1、uvicorn 0.54.0 的直接依赖声明，没有为了传输升级 MCP 或增加大型框架。

connect_transport 是一个小型 asynccontextmanager：stdio 分支按原有 PROJECT_DIR cwd 和 devnull stderr 创建 stdio_client；HTTP 分支创建显式安全 httpx2.AsyncClient，再传给 SDK 的 streamable_http_client。连接、进入和退出都由 Manager 的原 AsyncExitStack 管理，不用 asyncio.wait_for 包住上下文进入，不切换 owner Task。

## 7. 完整调用流程与 Phase 11 权限复用

```text
Gateway → validate_mcp → connect_transport
    stdio: SDK stdio_client → 子进程
    HTTP: 安全 AsyncClient → SDK streamable_http_client → 独立 Server
  → SDK Client(mode=legacy, cache=None) → initialize → tools/list
  → allowlist → MCPToolAdapter / Schema → 全部成功后统一注册

AgentLoop → ToolRegistry → Adapter.execute
  → Manager.call：owner / 本地策略 / 可用性 / Schema / 参数冻结
  → 原 authorize：allow / confirm / deny
  → SDK Client.call_tool → 对应 transport → Server
  → 原 Adapter.result → Plan.observe → 配对 Tool 消息 → Session / SessionStore
```

两种传输的同名工具通过 server 名隔离，如 mcp__local__add 与 mcp__web__add，不覆盖内置 add 以外的原生文件工具。发现期间先收集全部适配器，某个 Server 失败时释放已建立的所有连接，不留下半注册工具。

权限完全复用 Phase 11：缺省 confirm；deny 不注册，直接 Adapter/Manager 调用也拒绝；审批参数快照不可偷换；一次批准不跨调用复用。HTTP 没有单独的“已连接即授权”路径。拒绝后原 AgentLoop 补齐本批 Tool Result、停止后续工具、关闭未完成 Plan，并保存完整轮次。/clear 只重置原有 Session/Plan，不修改策略，不重放请求，不删除远端笔记。

## 8. 网络错误、取消与资源释放

连接拒绝、Endpoint 错误、401/403/404/5xx、初始化损坏、tools/list 失败、tools/call 失败、isError、等待超时和中途断开都通过真实网络测试。安全类别包括 http_connection_error、http_401、http_403、http_404、http_server_error、http_redirect_refused、timeout 或原 protocol_or_connection_error，不转发 URL、响应正文、Header 或原始异常。

SDK 的 HTTP 后台 worker 异常可能先触发 owner 取消，实际 ExceptionGroup 要到 AsyncExitStack.aclose 才抛出。Manager._close 在同一 Task 中完整退出上下文、清空 clients，收集清理异常，再转换为安全 ToolResult / MCPStartupError；真正的外部取消继续传播。清理阶段的错误也只暴露安全类别，不让原始网络 ExceptionGroup 漏到 CLI。普通业务异常仍保留其原有传播语义。

调用级网络故障关闭当前 Manager 的全部 MCP 连接，需用户重启，不自动重连。stdio 子进程随连接退出，HTTP Client/会话关闭，而独立 HTTP Server 继续运行。原生文件工具不受连接故障影响。

**超时不等于未执行。** 测试让 Server 先实际保存 actual-effect，再延迟 HTTP 响应。客户端超时并关闭连接，但新 Client 读到已保存笔记；记录证明只有一次 save_note 请求。因此失败回复明确写 remote effects may be unknown; no retry，不能声称没有副作用，不能盲目再次写入或删除。取消已发送请求也不能回滚效果。

## 9. Session、Context、审计与日志

HTTP 工具仍是普通 tool_calls / tool_call_id；Session 原文保留，SessionStore 的 JSON 版本和消息配对规则不变。Planning 只从真实成功 ToolResult 获取证据，拒绝/工具错误不能 verified。

ContextManager 对工具 Schema 与 Tool Result 使用原字符预算，无须理解 HTTP。测试实际发送模拟模型请求，验证 HTTP Schema 计入预算、长结果裁剪到请求副本，原 Session 中仍有适配器最多12000字符的结果。网络原始 JSON 大小和模型请求字符数是不同限制，不能把12000视为整个 HTTP 接收缓冲区上限。

SDK/network debug 日志可能带 URL、Session Header 和完整 JSON-RPC；HTTP 连接期间暂时抑制已加载的 mcp/httpx2/httpcore 协议日志，退出恢复原设置，使用 Manager 的安全类别与原有脱敏审计。当前单网关/串行使用，不支持并发 Manager 共用这些进程级日志设置。审计继续仅保存最近256条内存元数据，不写参数/笔记/URL。Session 仍可能明文持久化原始参数和结果，本阶段没有声称其已脱敏。

## 10. 自动化测试与实际结果

```bash
uv run python -m scripts.check_mcp_http
uv run python -m scripts.check_phase
uv run python -m scripts.test_phase_archives
uv run python -m compileall -q mybot
```

新增28项测试使用独立 loopback 端口、真实 Uvicorn HTTP 子进程和官方 MCP Server/Client。临时端口通过已绑定 socket 传给测试子进程，正常 MCP 交互都由 SDK 处理；ASGI 包装器仅记录合成测试元数据、注入 HTTP 错误/延迟，不替代协议实现。另有一项真实运行生产 Demo CLI。测试结束清理自己启动的 Server，Manager 本身不终止独立 Server。

覆盖：旧配置/严格字段/URL；真实初始化/list/add/echo；stateful JSON、SSE、stateless JSON；双传输/同名隔离/原子注册；allowlist/deny；批准保存、拒绝删除后内容保留、批准删除后内容消失；拒绝保存没有发送工具调用；冻结参数/Schema/不可复用批准；Plan/批量配对/clear；长结果和 Schema 预算；isError；401/403/404/500、503、错误 Endpoint、初始化损坏、list失败、连接拒绝；超时实际副作用/不重试；断连；取消/owner限制；实际 AsyncClient.is_closed、DELETE、Server存活；代理/netrc不继承；debug及审计隐私；Host/Origin；首次 GET 结束后不再发网络重连。

28项专项测试通过。全量 Phase 1–12 共184项 unittest 加 Phase 1/2 原有断言检查全部通过，详情见 AI_HANDOFF.md。归档设施另检查脏工作区、重复Tag/ZIP、路径穿越及敏感数据拒绝。没有调用真实 LLM API、第三方 MCP 服务或公网 HTTPS；真实模型自主选工具、远程 TLS/OAuth 兼容性没有得到这些离线测试的证明。

## 11. 常见问题、局限与相比 Phase 11 的变化

- 启动提示 HTTP 连接失败：先在另一个终端启动 Server，检查精确的 /mcp 与端口。模板同时配置两种 Server，启用后两者都要可达；不用的条目应从本地配置移除。
- localhost 被拒绝：本阶段只允许可静态验证的回环 IP；使用 127.0.0.1。HTTPS 必须由用户显式配置可信 Endpoint。
- 301/307 跳转失败：全部重定向拒绝；直接配置最终可信 Endpoint，不能接收工具结果推荐的地址自动迁移。
- 有状态 Server 的 Session 失效后不会自动 initialize；单个故障关闭所有 MCP，需要重启。GET 无网络重连、无断点恢复；可能需要这些能力的高级服务器未获兼容性保证。
- 未实现 OAuth/Bearer/Token刷新/旧SSE回退/认证配置/HTTP任意Header/服务发现，也没有承诺任意远程 Server 可用。
- 仅本地真实 HTTP 协议得到验证；远端 HTTPS 只有目标/证书校验配置路径，没有连接实际第三方服务测试。
- 12000是适配结果文本上限；SDK SSE事件默认1MiB上限，JSON响应没有本项目字节级大小沙箱。不把工具文字长度限制当作网络DoS防护。
- HTTP Demo 无认证，只适合本机可信学习；同一进程的笔记跨 HTTP Client 共享，不能用于多租户隔离。
- ExFAT 可产生 AppleDouble ._*，compileall 可能误读其为Python。仅识别文件头后清理元数据，归档排除，独立验证放在APFS临时目录，复制设置COPYFILE_DISABLE=1。

Phase 11 的权限、审批、审计及拒绝收尾没有新增第二套实现；本阶段只增加传输工厂、安全 HTTP 边界、独立 Demo 和 HTTP 故障的安全清理。没有升级协议语义，没有新 Agent 循环、长期记忆或 Phase 13 功能。

## 12. 保存和独立复习

```bash
# 从当前阶段提交的干净工作树执行，不覆盖旧归档：
bash scripts/save_phase.sh 12 "MCP Streamable HTTP and Multiple Transports"
bash scripts/restore_phase.sh 12
cd ../mybot-mini-learning/phase-12
uv sync --frozen
uv run python -m scripts.check_phase
```

Tag 为 phase-12；ZIP 为 ../mybot-mini-snapshots/phase-12.zip，含完整代码、Demo、示例、锁文件、技能、文档和离线测试，不含真实配置、Session、API Key、评测日志或用户未提交修改。独立冻结安装、编译、回归与还原结果最终记录到 AI_HANDOFF.md。

archive-ready: true
