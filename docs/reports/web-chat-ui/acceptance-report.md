# Web Chat UI 验收报告

结论：实现完成，OFFLINE PASS，真实浏览器验收完成。基线 `d4726669464bb83fd86d94e9ef31090dc4e7c782`，分支 `codex/web-chat-ui`，Implementation `027889b6831754f53647de32a82b1e00e9af78f7`。Acceptance SHA 为本报告所属提交，可用 `git log -1 --format=%H -- docs/reports/web-chat-ui/acceptance-report.md` 查询。独立分支交付，不合并 main、不创建 Phase/Tag/ZIP。

**真实模型 HTTP 请求：0。** 未使用任何旧 Benchmark 额度；没有付费模型连通性或模型行为成功率结论。正式入口直接连接既有模型客户端，合成客户端仅位于测试模块，通过显式测试工厂注入。

## 启动与真实使用

在本分支仓库根目录运行：

```bash
uv sync --frozen
uv run python -m mybot.web --port 8765
```

访问 **http://127.0.0.1:8765**。根据原配置模板填写本地 `config/config.json` 的真实模型/凭证及工作区；打开页面不会请求模型，发送消息后使用现有 OpenAI-compatible API。DeepSeek/GLM 回退沿用原配置。完整说明见 [Web 使用说明](../../web-ui.md)。真实配置不提交，原 CLI 继续可用。

## 最终架构与 Agent 接入

`__main__.py → Starlette server.py → ChatRuntime → AgentLoop.handle_message()`；浏览器通过受保护 HTTP 提交、SSE 接收真实事件，原模型返回后展示完整回复。无 CLI 子进程、stdin 模拟、print 解析或伪造 Token 流。

Runtime 复用 GatewayConfig、build_gateway_client/ProviderFailoverClient、ContextBuilder、Session、ToolRegistry、Skills、Planning、MCPClientManager、CodingTaskController、ApplyPatchTool、RunCommandTool 和 ChangeJournal。每轮创建原工具与 Agent，保留该对话 Session；MCP enter/call/exit 由同一个 owning task 执行。模型客户端每轮关闭，fallback sticky 范围为本轮，下一轮从主模型重新开始。

Loop 增加可选白名单事件观察回调，观察失败不影响原工具行为或授权。Plan 可静默原终端输出；CLI 缺省不开启回调。未修改原 Controller、Patch 发布器、Journal、命令/MCP 约束或 Strict 评分源码。

## 页面实际功能

中文桌面三栏：左侧新建/切换/历史/工作区/设置，中央聊天和多行输入，右侧可折叠任务活动。提供深浅主题、消息时间、复制回复/代码、基本安全 Markdown、表格/列表、代码高亮、长代码独立横向滚动、自动滚动及新消息提示。移动端侧栏与活动面板改为抽屉。

活动来自实际执行：模型请求、工具名称/状态/耗时、Plan 步骤、Patch Diff/文件摘要、测试状态和当前模型/Provider/逻辑请求数；缺失 Token 显示未知。普通聊天不堆积工具 JSON。Preview 明示未写入，只有原 Receipt 显式提交成功才显示发布；取消后仍保留后端已提交修改事实。当前 Revision 的 verified 来自 Controller，测试退出0不解释为整个任务 Strict Success。

## 审批、安全与隔离

原命令 inspectable_command、命令策略和 Seatbelt 自检保留。模态窗显示完整有效 argv、工作目录、模式、超时及隔离/副作用；保留 ASCII JSON 转义以显式呈现 bidi/control。host_confirm 明示无 OS 隔离。无法完整安全展示的请求拒绝。原 MCP confirm 接入相同浏览器审批，Web Undo 明确拒绝。

每次实际调用生成唯一有时限 nonce，验证当前对话及任务所有权，只能消费一次；无预批准、缓存、自动 yes。拒绝、Esc、取消、过期、重复或跨会话请求不授权。页面关闭不会批准，后端等待超时后拒绝。只保留类型/时间/决策脱敏审计。审批能力仅通过受保护的当前状态交付，不进入普通 SSE、URL、日志或 localStorage。

仅监听127.0.0.1；精确 Host/Origin、SameSite Strict/HttpOnly 进程 cookie、写请求 CSRF、SSE 授权、无任意 CORS、CSP、无访问日志、固定静态资源白名单。Markdown 只构造安全 DOM，原始 HTML/脚本为文本，拒绝危险协议链接。输入32KiB/16000字符、普通事件32KiB及有界文本/事件/会话；不提供任意文件读取或私有完整配置。

独立真实 Session，无 CLI 持久化读写；每进程20会话、每会话64条展示消息、每轮128条事件。Receipt、Controller、Plan 与工具 registry 按轮隔离。全进程只容纳一个活动 Agent 任务，并发返回 busy；停止真正 cancel 后等原清理屏障，再释放 workspace lease。执行/清理不确定时禁用新任务。刷新恢复已授权状态与 SSE 事件，不重放执行。

## 自动测试

| 检查 | 结果 |
| --- | --- |
| `uv run python -m scripts.check_web_ui` | 53/53 |
| `uv run python -m scripts.check_phase` | 1293/1293，35套件，零跳过 |
| 原有回归 | 1240项全部保留，入口仅追加新专项 |
| `uv run python -m compileall -q mybot scripts` | PASS |
| `git diff --check` | PASS |
| 正式单命令入口启动/首页/CSP/退出 | PASS；未发送消息，模型HTTP0 |

专项使用真实 AgentLoop 与合成 LLM，覆盖真实本地 HTTP/SSE、原生 Receipt/文件发布、Seatbelt unittest、真实 stdio MCP、上下文/会话隔离、清空、事件顺序、ProviderFailover、审批允许/拒绝/超时/nonce 重放/跨会话/bidi、取消及清理不确定、并发、输入及跨站安全、脱敏、验证状态及 CLI 兼容。数据见 [offline-validation.json](offline-validation.json)、[source-manifest.json](source-manifest.json)。日志仅保留 SHA256，原始内容不入库。

## 浏览器视觉与交互验收

实际使用内置浏览器打开 `scripts.check_web_ui --serve --plain` 临时离线 fixture，连接真实 AgentLoop/工具和一次性临时工作区，模型响应为合成。该入口不读取真实模型凭证，也不是正式产品默认路径。正式入口另做启动/首页/退出检查；不将合成回复冒充供应商真实结果。

实际检查1440×960桌面深浅主题、390×844手机、输入 Enter/Shift+Enter、空输入禁用、复制代码与剪贴板内容一致、表格/代码高亮、长代码滚动、历史切换/清空、刷新运行任务后停止、移动侧栏和可折叠活动。DOM检查：危险 script 0、危险链接0、语法关键字节点4、表格1；注入 HTML/javascript 链接显示为文字。手机页面宽/scrollWidth 均390，代码区域339/1395，实际横向滚动位置140。

临时修复流程实际执行 read_file_range、Patch Preview、Receipt 显式提交；审批弹窗展示原安全 macos_readonly unittest 命令，浏览器人工点击“允许本次执行”1次，原 Seatbelt unittest 退出0。TTY yes 0，无后台代批准真实用户任务。工具耗时包含等待审批。浏览器 fixture 已关闭。

以下均为实际页面截图；桌面 JPEG 压缩降低小字清晰度，文字/状态另以 DOM 与专项测试核实：

| 截图 | 内容 |
| --- | --- |
| [desktop-dark.jpg](screenshots/desktop-dark.jpg) | 深色三栏与欢迎页 |
| [desktop-light.jpg](screenshots/desktop-light.jpg) | 浅色三栏 |
| [desktop-chat.jpg](screenshots/desktop-chat.jpg) | Markdown、代码、表格与安全文本 |
| [mobile-chat.jpg](screenshots/mobile-chat.jpg) | 手机布局与代码横向滚动 |
| [approval.jpg](screenshots/approval.jpg) | 实际原生命令待审批 |
| [patch-and-tests.jpg](screenshots/patch-and-tests.jpg) | Preview/Commit/测试真实工具状态 |

量化观察及截图哈希见 [browser-acceptance.json](browser-acceptance.json)。

## 保护资产及提交审查

1043个历史保护文件哈希不变，main 与26个 Tag 不变；53个 ZIP/AppleDouble、原13个及最近8个 Attempt raw、既有 Phase/报告/Campaign 均保留。检查跟踪文件及本轮新增文件，无真实凭证、实际配置、Session、缓存、虚拟环境、AppleDouble 或不必要大文件入库。测试中的公开 synthetic canary 是显式假值。细节见 [security-audit.json](security-audit.json)。原主工作区两处用户修改未触碰。

Git 对 ExFAT 历史 AppleDouble pack 索引会报告 non-monotonic 警告；不删除或改写用户 Git 资产，实际对象访问、测试、提交正常。独立 worktree 在 APFS；本轮截图按字节复制，不引入 AppleDouble。

## 已知限制与后续扩展

- Web 对话仅内存，服务重启丢失；不支持附件、上传、磁盘历史、Web Undo、公网账号或多租户。
- 单任务 lease 仅在本服务进程有效，其他 CLI/Web 进程仍需用户避免同时修改同一工作区。
- 基础 Markdown/高亮，不支持数学排版或完整扩展；非 Token 流式。工具事件/文本和 Diff 可截断并标记。
- 命令审批默认90秒，整体任务默认600秒；供应商模型超时沿用原配置。页面关闭不会自动取消任务或授权，审批会超时拒绝。
- 没有真实付费模型连通性测试，实际供应商 schema、响应行为和费用留给用户正式配置后验证；当前离线通过不代表 Strict 或真实成功率。
- 后续可按需增加安全持久化、更多 Markdown、真正 Token 流、跨进程工作区锁及受控 Undo；须保留原工具审批和取消清理语义。
