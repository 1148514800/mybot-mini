# mybot-mini 本地 Web Chat

在仓库根目录安装依赖并启动：

```bash
uv sync --frozen
uv run python -m mybot.web --port 8765
```

浏览器访问 **http://127.0.0.1:8765**。入口只监听 IPv4 loopback，没有公网/LAN host 选项，不支持反向代理。原 CLI `uv run python -m mybot.main` 保持可用。不要让不同 Web 进程或 CLI 同时修改同一个工作区；跨进程执行仍使用原 WorkspaceLease。

## 连接真实模型

正式入口没有模拟回复或测试客户端。它读取原有 `config/config.json`，使用 `build_gateway_client()`、现有 OpenAI-compatible 客户端及 DeepSeek → GLM 回退。首次使用可从 `config/config.example.json` 复制本地配置，按原 README 填写 provider、model、base_url 和 api_key。真实配置不要提交。浏览器不接收 API Key，也不提供修改模型凭证或提升工具权限的接口。

打开页面不请求模型；发送消息才调用真实 `AgentLoop.handle_message()`，因此用户配置服务后发送消息会产生相应模型费用。本轮开发没有发送真实模型请求。模型目前不是 Token 级流式返回：UI 通过 SSE 展示真实阶段事件，模型返回后一次显示完整回复，不模拟打字。

如需修改代码和可信测试，在原有配置中显式启用 Coding（工作区必须已存在），例如合并以下部分，而不是覆盖 llm 配置：

```json
{
  "workspace": {"path": "/absolute/path/to/your/project"},
  "coding": {
    "enabled": true,
    "patch_mode": "write",
    "preview_receipt": true,
    "command": {"mode": "macos_readonly", "timeout_seconds": 30},
    "autonomy": {"enabled": true},
    "git_workflow": {"enabled": true, "undo_enabled": false}
  }
}
```

工具能力仍由原配置决定，Web 不自动开启 Write、命令或 MCP。普通模式沿用基础文件工具；Coding 模式沿用原生 ApplyPatchTool、RunCommandTool、Controller 和 Journal。Receipt 只在模型请求中传递，不显示到 UI；Preview 卡片明确标为未写入，正式 Commit 才显示发布成功。测试退出 0 不等于任务验证；当前 Revision 的可信测试结论只取原 Controller 报告，绝不称为 Strict Success。

## 页面操作

左侧新建和切换独立对话，中央 Enter 发送、Shift+Enter 换行，运行时点击“停止”。停止会请求实际取消，并等待 Agent、MCP 和模型客户端清理完成；期间工作区继续占用。若无法确认清理或执行结果，会阻止新任务，需人工检查后重启服务。并发发送返回 busy，不排队执行或自动重试。

右侧活动面板可折叠，显示当前任务的逻辑请求次数、已报告 Token（不可获取时标为未知）和单独的输入估算、真实工具卡片、Plan、Diff、修改文件及后端测试状态。工具耗时包括等待审批的时间；取消而未返回的工具显示中断，不伪造成功。底部自动滚动；上滚后可点击新消息提示返回。代码与回复可复制，长代码独立横向滚动。支持基本 Markdown 标题、粗体、列表、引用、表格、代码与基础语法高亮；原始 HTML/图片不执行，不支持数学排版或全部 Markdown 扩展。

深色为默认，唯一localStorage内容是主题。默认memory，重启不保存；显式session.backend=event_sqlite后恢复标题/消息/状态，普通聊天和Pin存本地明文SQLite。每次展示最近64条，可“查看更早消息”，会话列表最多20，活动事件128。CLI/Web共享引擎但命名空间隔离，不读取旧CLI JSON；persist=true的旧配置不会自动打开Web持久化。刷新/SSE只恢复当前状态，不重放工具。

用户消息“固定此消息片段”打开确认弹窗，可选择类别及显式替换旧项；活动面板显示来源、状态修订和进入预算的结果。撤销/替换只影响新请求，历史可审计；预算不足会警示遗漏。Pin不提升工具能力或恢复旧验证。配置与限制见[会话后端](reports/session-eventstore-pinned-context/legacy-session-compatibility.md)。

“设置与连接”可清除当前模型上下文；SQLite模式保留聊天和Pin，只有明确确认“删除会话”才删除数据库记录。底层存储、备份可能残留，不保证物理擦除。执行不确定时先人工检查工作区/残留进程，再显式复核；不会恢复旧verified或授权。仅空闲时允许这些操作。第一版不保留跨轮 Undo capsule，`/undo`、`/changes` 明确拒绝；查看当前修改请用活动面板。原 CLI Undo 不受影响。MCP 按原配置启动，confirm 策略调用通过同一 Web 审批；连接、调用、关闭留在原 manager 的同一个 owning task 中。

## 每次审批

命令弹窗展示原 `inspectable_command` 生成的完整有效 argv、工作目录、模式、超时和隔离说明；保留 ASCII JSON 转义，防止控制符/bidi 隐藏命令。无法完整安全显示、含已知凭证或能力的请求直接拒绝。`host_confirm` 明示无 OS 隔离和外部副作用；`macos_readonly` 仍执行原 Seatbelt 自检、只读工作区和网络限制。

批准只对应当前实际等待的一次调用：随机 nonce 有时限，只能消费一次；拒绝、Esc、取消、超时、旧 nonce、跨对话、重复批准都不能变成授权。刷新可重新查看同一未过期请求；关闭页面不会自动批准，最多等到后端超时拒绝。没有预批准、授权缓存或自动 yes。必要审计只有类型、决策、时间，不保存 nonce 和完整命令。正常使用时必须由用户亲自点击批准。

## 本地安全与实现

`mybot/web/server.py` 提供 Starlette ASGI、固定静态资源、HTTP API 与 SSE。Host 和 Origin 必须匹配 127.0.0.1:启动端口，禁止跨站请求和任意 CORS；HttpOnly/SameSite=Strict 进程级浏览器 cookie 授权读取，写请求还需同源 Origin 与 CSRF header。SSE 同样检查授权，URL 不放认证令牌，访问日志关闭。CSP 禁止内联/外部脚本和 iframe，Markdown 仅构造文本 DOM，链接仅允许不含凭证的 http/https。不提供任意本地文件读取接口。

请求体最多32 KiB，消息最多16000字符（仍受传输字节上限）；普通事件有32 KiB上限，UI文本有32 KiB UTF-8上限，历史与会话数量固定有界。代码 Diff 可截断并显示标记，不因此声称完整审阅。普通事件只传白名单元数据，工具参数、SDK异常原文、Receipt、完整私有配置不进入事件；凭证与能力做额外脱敏。审批 nonce 只经受保护的状态响应给当前浏览器，不进普通事件或 localStorage。

`runtime.py` 为每轮创建原 Agent、独立工具 registry、MCP owner 和模型客户端，保留该对话的真实 Session；进程内任务占用与跨进程工作区锁均在清理屏障后释放。模型客户端按轮关闭，fallback 的 sticky 范围是该轮，下一轮重新按配置主模型开始；不是跨轮共用 CLI 客户端。Skills、Planning、MCP、Controller、Receipt 和 Journal 都走既有实现；原生写入器、验证与审批政策未替换。活动回调是可选且不参与授权，CLI 缺省关闭；Web 静默 Plan 的 print 输出，不解析 CLI 日志。

本地单用户模式不提供公网账号、多租户、文件上传或附件。不要转发端口到公网，也不要把本地浏览器授权视为不同 OS 用户之间的安全隔离。

## 验证

```bash
uv run python -m scripts.check_web_ui
uv run python -m scripts.check_phase
uv run python -m compileall -q mybot scripts
git diff --check
```

专项通过真实 AgentLoop、原生文件/Receipt/命令、真实 Seatbelt、真实 stdio MCP 与本地 HTTP/SSE，只有模型响应是合成。`scripts.check_web_ui --serve`（可加 `--plain`）是明确的临时离线浏览器验收 fixture，端口8877，绝非正式入口；它不读取真实模型凭证、不请求付费模型。验收结果与截图见 `docs/reports/web-chat-ui/acceptance-report.md`。

## 新资源指标与工作区协调

活动面板把“已报告 Token”与“当前输入估算”分开展示，缺失 Usage 或模型窗口显示未知。逻辑请求包含摘要请求；物理调用包含回退，HTTP 尝试只在 transport 可观察时显示数值。摘要模式、保留/摘要轮数和裁剪警示不会展示原始摘要、模型敏感配置或有效 Receipt。失败计划不会显示已完成，模型回答结束不等于代码验证成功。

按 [Context 配置](context.md) 启用估算预算或选择性语义摘要后重启服务。规则摘要仍是默认；语义模式显式允许额外调用才可启用，真实费用未知。

同一工作区已有 CLI/Web 持锁时，新任务安全失败且不发送模型请求。CLI 等待输入期间也持锁；退出后才可由 Web 使用。清理不确定时不要删除锁绕过，确认进程退出后再启动。Web默认内存，可显式SQLite；不复用CLI SessionStore。

## 任务要求与验证

普通聊天默认不提供 write_file。只有显式 legacy_confirm 才会出现完整内容的一次性文件审批；
与原生 Patch 互斥，缺失或无法安全展示审批则拒绝。命令/MCP 仍使用其独立审批。

自主编码任务启用 coding.task_contract 后，活动面板提供可折叠“任务要求与验证”。
“真实测试记录关联，覆盖未知”只证明已观察到当前 Revision 的指定测试，不等于需求独立验收通过。
没有独立验收时 Task Correctness 保持 unknown。需求简述从页面已脱敏的当前用户消息还原，事件只发送字符坐标；
脱敏导致长度改变时显示需求编号，项目文档条目也仅显示编号/类别。取消、预算耗尽及缺少合同时如实保留未完成状态。
合同不跨任务恢复，也不恢复授权。完整解释见 [证据等级](reports/tool-authority-task-contract/requirement-evidence.md)。
