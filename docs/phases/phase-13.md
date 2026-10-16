# Phase 13：MCP Bearer Authentication & HTTP Response Security

## 1. 学习目标与前置知识

本阶段在 Phase 12 的 Streamable HTTP 传输边界内增加静态 Bearer 认证和网络响应接收限制。目标是理解 Authentication、Credential Provider、Credential Isolation、流式接收和 Fail-Closed，并能解释：为什么工具输出截断不能阻止网络输入耗尽内存，为什么认证成功不代表允许写笔记。

运行环境为 macOS/zsh、Python 3.12+、uv。锁定 MCP/mcp-types 2.3.0、httpx2 2.13.1；没有升级依赖。学习前应理解 Phase 10 的 SDK Client/Adapter、Phase 11 的审批、Phase 12 的 owner Task 与 HTTPBoundary。既有 AgentLoop、ToolRegistry、Planning、Session、MCPToolAdapter、Approval 和 Manager 逻辑均复用。

## 2. Authentication 与 Authorization

Authentication 回答“HTTP 调用方是否持有服务器接受的凭证”；Authorization 回答“本地 Agent 是否允许执行这次工具操作”。Demo 的 Bearer 校验只处理第一个问题，Phase 11 的 allow/confirm/deny 继续处理第二个问题。即使已成功 initialize/list，save_note 仍须逐次审批；deny 工具不会注册，也不能通过 Manager 绕过。

Bearer 意味着持有即可使用，不要求另一个私钥证明。HTTP Header 使用 `Authorization: Bearer TOKEN`，避免将 Token 放入 URL query、工具参数或 JSON-RPC 正文。Bearer 字符语法和 Header 用法参考 [RFC 6750 §2.1](https://www.rfc-editor.org/rfc/rfc6750.html#section-2.1)。本项目仅使用该认证格式，并没有实现 OAuth 授权流程。

完整 MCP OAuth 体系还需要授权服务器、授权与令牌端点、发现、适用的 PKCE/资源受众等协议能力。本阶段没有浏览器登录、授权码交换、自动刷新、Scope 扩大或 OAuth 回退。401 后由用户检查本地凭证；不能把静态环境变量认证称为 OAuth 登录。

## 3. 本地配置与 Credential Provider

HTTP Server 配置允许省略 auth（等价于 `{"type":"none"}`），或指定唯一支持的凭证引用：

```json
{
  "transport": "streamable_http",
  "url": "https://example.com/mcp",
  "auth": {"type": "bearer_env", "token_env": "MYBOT_MCP_TOKEN"},
  "allowed_tools": ["add", "echo"],
  "tool_policies": {"add": "allow", "echo": "allow"},
  "timeout_seconds": 10
}
```

example.com 仅为配置说明，测试从未连接它。真实 config/config.json 不进 Git。模板的 demo-http 显式配置 none；需要认证时将该对象替换为 bearer_env。stdio 拒绝任何 auth 字段，包括 none；不允许任意 headers、access_token、refresh_token、client_secret 或 Token 明文。

`credentials.validate_auth()` 严格校验字段集合。环境变量名使用 `[A-Za-z_][A-Za-z0-9_]{0,127}`，只允许字母/下划线开头、最多128字符的本地引用。不会展开变量、shell 表达式或读取其他凭证来源。

`load_credential()` 在连接建立时读取指定环境变量，缺失为 credential_missing；空值、空白、换行、控制字符、非ASCII、不符合 RFC b64token 或长度超过4096的值为 credential_invalid。合法字符为字母数字及 `._~+/-`，可带末尾 `=`。ASCII 约束下字符数等于字节数。

返回冻结的 Credential 快照，Token 字段不参与 repr；`apply(headers)` 只供传输边界使用。不把它放入 config 副本、Schema、工具 arguments、模型请求、Session 或审计。环境变量修改后必须重启 Gateway；已建连接的 POST/GET/DELETE 使用同一快照。环境变量仍可被本机进程/调试器读取，不是操作系统 Secret Vault，也没有宣称内存安全擦除。

## 4. 请求发送边界与调用关系

```text
AgentLoop → ToolRegistry → MCPToolAdapter.execute
  → MCPClientManager.call
  → 校验并冻结 arguments → Phase 11 PermissionGate
  → SDK tools/call
  → HTTPBoundary.request
      精确 Endpoint 校验 → 禁止 GET 恢复
      → 移除外来身份 Header → 注入可信 Bearer
  → ResponseLimitTransport → HTTP MCP Server
  ← 原始响应流限制 ← httpx 解码 ← SDK JSON/SSE ← Adapter
```

`connect_transport()` 读取凭证后构建 HTTPBoundary。request hook 在发送前检查实际 URL 与本地固定 Endpoint 完全相同，再检查首次 GET/Last-Event-ID。随后清除 Authorization、Proxy-Authorization、Cookie；设置 Accept-Encoding: identity；最后才调用 Credential.apply。顺序很重要，否则旧清理逻辑会删掉新认证，或外来 Header 覆盖可信凭证。

每个配置 Server 有独立 Client、Boundary、Credential；没有认证配置的 Server 不会继承其他 Server 的 Token。Header 注入对 POST、合法首次 GET、Session DELETE 一致。非目标 Origin、路径或 query 请求在网络发送前拒绝，全部重定向仍拒绝。URL 不接受 userinfo/query/fragment，明文 HTTP 仍只允许字面量 loopback；HTTPS 使用默认正常证书验证，未开放 verify=False。

保持 trust_env=False、auth=None、无环境代理/netrc、无重试、无网络 GET 恢复。工具结果不能修改 URL 或认证配置。SDK/network debug 日志继续按 Phase 12 暂时抑制，连接退出恢复；进程级 logger 设置仍只适合当前单 Gateway 模式。

## 5. 真正的响应接收上限

Adapter 的12000字符限制处理“已经接收并解码后的结果”，不是网络字节预算。本阶段在 httpx2 的 AsyncBaseTransport 外包一层 ResponseLimitTransport，底层为原来的 AsyncHTTPTransport。锁定版本的 handle_async_request 返回未缓冲的 Response.stream，后续 httpx `aiter_raw → aiter_bytes → aread` 才消费它；因此可以在 SDK 缓冲/JSON 解码之前拦截。

`ResponseLimitTransport.handle_async_request()` 先检查 Content-Encoding，只接受缺省/identity，其他编码立即关闭响应并返回 http_content_encoding_refused。即使服务端忽略 Accept-Encoding，也不能把 gzip/br/deflate 等压缩数据送进解压器形成膨胀绕过。压缩 SSE 同样拒绝；不支持压缩响应是明确的兼容限制。

对 media type 不是 text/event-stream 的所有响应（包括未知/缺省 Content-Type），将 stream 替换为 LimitedStream，默认 `MAX_HTTP_JSON_BYTES = 2 * 1024 * 1024`。LimitedStream 逐块累计实际原始字节；累计超过阈值就抛固定 http_response_too_large，**超限块不会交给 httpx/SDK，后续块不再读取**。finally 关闭底层 stream；aclose 幂等。没有额外正文副本，也没有事后 len(response.content) 检查。

不依赖 Content-Length；缺失、chunked、虚报大小都无法取消计数。正好2MiB可通过。TCP/HTTP底层仍可能已接收一个超限块及系统缓冲，SDK缓冲在阈值内；这是响应输入限制，不是进程总内存上限、完整网络DoS沙箱或并发/时间预算。

未压缩 text/event-stream 不累计整个流，否则合法长连接总会超限；继续交给 MCP 2.3.0 默认1MiB单事件限制。测试覆盖总量超过2MiB的小型 SSE 块和真正超大单事件，不能把“无限 SSE 总量不限制”解读成无限事件缓冲。

## 6. 错误、关闭与副作用

| 安全类别 | 含义与处理 |
| --- | --- |
| credential_missing | 指定环境变量不存在；连接前终止，不匿名降级 |
| credential_invalid | 值不满足字符/长度约束；连接前终止 |
| http_401 | Server 拒绝凭证；不 OAuth、不刷新、不重试 |
| http_403 | Server 拒绝访问；不扩 Scope、不重试 |
| http_connection_error | 建连/网络请求失败 |
| timeout | 等待超过既有 SDK/HTTP 超时 |
| http_response_too_large | 非 SSE 实际字节超限，关闭响应和 Manager 连接 |
| http_content_encoding_refused | 非 identity 编码，读取/解压前拒绝 |
| http_target_refused / http_redirect_refused | 非配置 Endpoint / 重定向被拒绝 |

401/403 的 response hook 检查适用于 POST/GET/DELETE；合法非POST的405继续兼容 SDK 对可选流/会话能力的处理。既有 Manager.failure_kind 识别共享 HTTPTransportError，错误类型移入 errors.py，并从 transport.py 保留导入兼容。错误消息不包含原始 Body、Header、Token 或外部异常文本。

初始化/发现阶段失败调用原有 AsyncExitStack 清理，不注册半套工具；如果此前已开启 stdio 也会释放其子进程。tools/call 失败关闭所有 MCP，沿用“远端副作用可能未知、无重试、需重启”的提示。进入 SDK、调用和退出仍在同一 owner Task；没有 wait_for 包裹上下文进入。取消可以关闭本地连接，但不能回滚已送达远端的数据或证明服务端没有执行写入。

## 7. 核心文件和关键函数

| 文件 | 作用 |
| --- | --- |
| mybot/mcp_client/config.py | validate_mcp 按传输允许 auth，并调用 validate_auth |
| mybot/mcp_client/credentials.py | validate_auth、load_credential、隐藏repr的 Credential |
| mybot/mcp_client/errors.py | 不带外部数据的共享 HTTPTransportError |
| mybot/mcp_client/transport.py | connect_transport、HTTPBoundary.request/response；沿用 quiet_wire_logs |
| mybot/mcp_client/response_limit.py | ResponseLimitTransport、LimitedStream；计数、拒绝编码、关闭 |
| scripts/mcp_http_demo_server.py | create_app 可选认证中间件；CLI --require-token-env |
| scripts/check_mcp_auth.py | 真实SDK/HTTP专项和对抗式字节流注入 |
| scripts/check_phase.py | 将认证专项加入全量回归及归档自验证 |
| config/config.example.json | 保持MCP关闭，HTTP示例显式 none |

Manager、Adapter、Approval、AgentLoop 等未增加第二套认证或审批实现；它们的原理和架构仍以 Phase 10–12 文档为前置知识。

## 8. macOS + uv 本地学习步骤

```bash
uv sync --frozen
# 终端A：以下值只是公开的本地教学合成凭证，不能用生产凭证代替
export MYBOT_MCP_DEMO_TOKEN='test-local-token'
uv run python -m scripts.mcp_http_demo_server --port 8765 \
  --require-token-env MYBOT_MCP_DEMO_TOKEN
```

终端B：

```bash
cp config/config.example.json config/config.json
export MYBOT_MCP_DEMO_TOKEN='test-local-token'
# 只在本地编辑配置：mcp.enabled=true；移除不用的stdio Server
# demo-http 的 auth 改为：
# {"type":"bearer_env","token_env":"MYBOT_MCP_DEMO_TOKEN"}
# 真实交互还需自行配置 LLM API；以下 CLI 会使用该配置
uv run python mybot/main.py
```

不需要真实模型即可运行以下验证；测试自行启动本地 Server/stdio 子进程并清理：

```bash
uv run python -m scripts.check_mcp_auth
uv run python -m scripts.check_phase
uv run python -m scripts.test_phase_archives
uv run python -m compileall -q mybot
```

本阶段测试没有执行上面的真实 LLM 交互命令，也未读取实际 Token。无认证学习仍可直接启动不带 --require-token-env 的 Demo，并使用省略auth/none的配置。

## 9. 实际案例与测试结果

新增38项专项：32项 Authentication/真实HTTP集成检查、6项底层接收检查。Phase 1–13 全量共222项 unittest，另含 Phase 1/2 断言；全部通过。归档安全集成检查通过。完整ZIP的冻结安装、编译和全量回归、独立还原验证结果见 AI_HANDOFF.md。

实际案例：

- 正确合成凭证完成 initialize/list/add/echo；追踪证实 POST/GET/DELETE 均认证且使用 identity，正文不含凭证。错误/无凭证401，initialize只发送一次。
- 认证后拒绝 save_note，追踪无写调用，read_note 无笔记；批准后 read_note 读到实际内容；deny 不注册且 Manager 也拒绝。
- tools/call 注入401/403，各只发一次，报告安全类别及副作用未知，AsyncClient.is_closed 为真。初始化/发现超限同样无半注册。
- 有声明大长度、无 Content-Length 的真实 chunked JSON 均被拒绝；真实gzip在解压前拒绝。小型 JSON 正常、未压缩 SSE 正常，包含合法JSON-RPC结果的SDK超大事件继续因单事件保护而失败。
- 伪造 Content-Length 通过合成 AsyncBaseTransport 注入：底层 HTTP/1.1 栈会按 framing 处理较小声明或拒绝额外字节，因此不能要求 Uvicorn 发送一个违反长度声明的合法响应来证明计数。独立注入证明 wrapper 不相信长度：64KiB块只交付32块，第33块报错，第34块起不读，stream立即关闭。没有把协议 framing 拒绝冒充接收上限成功。
- 两个真实 Server 同时连接，有认证者得到显式凭证，无认证者没有 Authorization。保留 stdio/HTTP 混合管理；后一个 Server 缺凭证时前一个 stdio进程已退出。
- DEBUG日志、审计、模型请求、工具Schema、内存Session和临时持久化Session均未注入凭证；环境代理/netrc不改变请求认证。HTTP故障正文和重定向均不回显凭证。
- 取消真实写调用或底层响应读取均释放Client/stream；独立Server继续存活，测试清理自己启动的进程。

## 10. 常见问题、限制与 Phase 12 → 13 变化

- credential_missing：环境变量要设置在启动Gateway的同一终端/进程中；配置引用与Server期望值一致。环境变更后重启，不能靠下一次工具调用自动轮换。
- credential_invalid：不要在值中加入 `Bearer ` 前缀、空格、换行；值最大4096 ASCII字节。不要通过放宽Header校验解决问题。
- 401与403不同：前者检查凭证有效性，后者检查服务端访问权限；本地confirm仍必须单独通过。Demo对无/错误凭证统一401，不泄漏对比值；通过hmac.compare_digest比较并拒绝多个Authorization。
- http_content_encoding_refused：服务端必须提供identity响应；本阶段没有支持压缩解码预算。
- http_response_too_large：需要服务端缩小JSON/结果，不把部分JSON解释为成功，不自动重试。
- 学习Demo是本机单进程内存工具，没有真实文件写入、联网或多租户隔离，不是完整OAuth Resource Server。HTTP明文仅适合本机合成Token测试，生产凭证应使用用户预先确认受众/目标的HTTPS服务；禁止把其他服务Token直接转发。
- TLS证书校验不代表服务器行为可信；HTTP服务器能保存已收到的数据。Session仍可能保存Function Calling参数/结果；如果用户主动把秘密写入参数，认证隔离不会替其脱敏。
- 静态Token无自动刷新/撤销同步/轮换；环境变量不是Vault；网络字节预算不是完整DoS沙箱。SSE没有总流量上限，保留默认单事件保护与既有超时。
- 只验证真实本地HTTP和离线模拟模型，没有连接公网HTTPS/第三方MCP/真实LLM；没有证明远端TLS服务或真实模型选工具效果。
- macOS ExFAT可能生成 `._*`，compileall会将 `._*.py` 当源码。只清理文件头确认为AppleDouble的元数据，复制设置COPYFILE_DISABLE=1；归档排除并优先在APFS临时目录验证，不能承诺系统永不生成。

相较 Phase 12，认证从始终移除身份Header变为“移除后按显式本地引用注入”；新增网络非SSE字节限制和压缩拒绝。URL/重定向/代理约束、工具审批和Agent架构均保持原有边界。不进入Phase 14。

## 11. 保存、还原与复习

```bash
# 仅在包含本阶段文档的干净已提交版本执行；不覆盖旧Tag/ZIP
bash scripts/save_phase.sh 13 "MCP Bearer Authentication and HTTP Response Security"
bash scripts/restore_phase.sh 13
cd ../mybot-mini-learning/phase-13
uv sync --frozen
uv run python -m compileall -q mybot
uv run python -m scripts.check_phase
```

Tag为唯一annotated phase-13，ZIP为 ../mybot-mini-snapshots/phase-13.zip。主工作区有用户未提交修改时，在APFS干净独立worktree归档确切提交；ZIP仅含已提交完整源码，不包含用户修改、真实config、Session、日志或凭证。旧Phase 1–12归档保持不变；不自动push。

archive-ready: true
