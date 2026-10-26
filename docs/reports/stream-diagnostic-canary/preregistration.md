# Streaming Diagnostic Canary v1 — D01

LIVE_AUTHORIZATION: NOT_GRANTED

基线 `ba759de36418d67008e98c8c7ddf05566dc520e5`，独立分支 `codex/stream-diagnostic-canary`。只允许未来用户明确 `GRANTED_1_REQUEST` 后启动一次。原R01 FAIL/provider_error、Case running、HALT和旧7次余量不继承、不修改、不补跑。

唯一批次 `~/.mybot-mini/uat/stream-diagnostic-canary-20261026/`；若存在不得prepare覆盖。唯一prepare、唯一freeze。源码、完整合同、配置原字节指纹、Workspace字节与inode、事件库和账本inode、浏览器隔离证据均校验。原本地Provider配置路径仅保存在私有prepared.json；不复制凭证。冻结提交为包含本合同和完整脚本的Preregistration commit；后续Acceptance只改文档。

## 唯一输入

> 请分六个简短自然段介绍一个完全离线运行的日志检索工具，包括用途、输入格式、索引方式、查询方式、结果展示和使用限制。每段后换行。不调用工具，不读取、修改或删除文件。

D01一个Attempt、新独立Session，端口127.0.0.1:8899。coco / deepseek-v4.1-flash；备用原策略为coco2 / glm-5.3-flash，但任何第二次物理发送必须被预算拒绝。Streaming enabled、Steer disabled、stream=True、stream_options.include_usage=True；SDK retries=0。空Registry，MCP/Skills/Coding关闭，语义摘要/Judge禁用。单Agent步、估算输入上限14000、输出预留1200、超时90秒；不声称知道部署窗口。

全局与D01均最多1次物理请求，包含失败、备用、任何实际HTTP尝试；不得转移历史余量。SQLite BEGIN IMMEDIATE在SDK前预留，HTTP hook在transport前持久记数，重复HTTP拒绝。SDK创建但未发送也保守占用额度。原RuntimeAccounting可能将被拒绝的备用准入记录为physical record；报告必须分别列准入记录、账本reservation与实际HTTP，不能把未发送备用当成第二次真实请求。

## 正式路径与操作顺序

create_app → ChatRuntime → AgentLoop → ProviderFailover → SDK Streaming不替换。只在本次自有服务生命周期内复用ReadRegistry限制为空；原AgentLoop试图注册planning也被省略，无模型权限扩大。Transparent observer不改Chunk、顺序或增加时序屏障。

授权后先运行`uv run python -m scripts.stream_diagnostic_canary.prepare verify --provider-config <prepared.json中的原配置路径>`。重新确认真实PID/UID/cwd/argv、8899空闲、WorkspaceLease、数据库、0 Attempt/0 reservation、冻结hash及新0700浏览器profile。不得读旧聊天或触碰8765。

以`uv run python -m scripts.stream_diagnostic_canary.server --provider-config <原路径> --authorization GRANTED_1_REQUEST`启动；当前无授权禁止执行。启动即占唯一Attempt，未发消息退出也不能重启补跑。新鲜Chrome profile由Playwright控制，真实DOM新会话、输入唯一文本、点击发送一次。不重发、不追加提示、不改参数、不回落非流式。只读状态可核验；页面Cookie/CSRF来自本服务原入口，不绕过认证。浏览器记录performance.now点击与首次可见文本，首Chunk/文本/SSE宿主发送时刻使用server monotonic；跨时钟延迟UNKNOWN。

收集终态与结算后，有界正常关闭本次拥有的服务。先SIGINT自己launcher；必要时仅再次核验PID/UID/PPID/启动时间/完整argv/cwd/监听端口完全一致的子进程，发送SIGINT。复用local_web_process身份规则，但Live CLI参数须按真实argv核验，不能套用Mock入口参数。不得SIGKILL、批量终止、删锁。必须wait取得exit0，核对端口、Lease、SQLite；只端口消失不能PASS。失败/HALT不经过新请求准入门阻止原生runtime.close；不删除HALT或把failed写成passed。

## 独立评分

- Protocol PASS：正常消费、合法终态、自然EOF、SDK关闭确认、无未解决协议错误，且最终文本经原生规范化后的哈希与SQLite持久助手回复匹配。只有stop、预览、GeneratorExit任何单项均不足。
- Protocol FAIL：保留StreamErrorCode、Chunk序号、处理阶段、最多8块结构摘要、EOF/close。不能由错误码归责部署或本地验证器。HTTP打开前失败没有SDK Chunk时，不虚构StreamErrorCode/Chunk序号。
- Usage：完整原供应商字段才称真实Usage；缺失UNKNOWN独立列，不自动协议FAIL，也不能Usage兼容PASS。cost=null直到可信价格可核对；1次请求不是美元硬上限。
- UX：独立判断可见预览是否先于完成，浏览器同钟耗时。SSE宿主emit不是网络到达时间。
- Clean Shutdown：exit0、SDK流关闭、端口释放、Lease释放、SQLite一致均成立。不能用cleanup.json内的待定exit字段替代操作员wait结果。

协议拒绝后停止新请求并保留新HALT。冻结、预算、凭证、数据或执行状态不确定立即停止，不补跑、不修改标准。即使D01成功，也不自动测试Steer或保证长期兼容。

## 数据边界与离线证明

不保存完整模型请求、原始Chunk、私有回复正文副本、工具参数或凭证到诊断/报告。原生私有事件库必须持久化最终回复以验证可靠保存，但不导出/提交其正文或SQLite。Observer只在有界内存中暂存文本用于原生strip哈希比较；最多8块结构元数据来自正式consumer，不是猜测协议原因。Cookie/CSRF、Profile、nonce、调试数据不提交。失败Usage、缺失字段不以Token估算填充。

离线用MockTransport真正走SDK消费及同一Web harness，另建临时数据，不接触新Live账本。33项新增专项及219项相关既有测试通过；真实headed Chrome双profile隔离、正常/拒绝流页面及打开SSE时exit0实测通过。合成证据不算D01 Live Attempt。
