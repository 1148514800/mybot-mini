# D02 — stream-legacy-canary preregistration

LIVE_AUTHORIZATION: NOT_GRANTED

本轮真实模型上限0；未来只有新收到的精确GRANTED_1_REQUEST才允许D02一次Live。旧D01已耗尽的授权与1/1、旧R01剩余7次均不能继承。本合同不改变历史FAIL/HALT，不运行任何旧Case。

基线72e5ef74fb574dc9212fca188112ef058e4762e1；Implementation `3a906311a196f23e01227fd3ec9f0b212047b70b`；本合同由独立Preregistration提交冻结。独立分支codex/stream-legacy-function-compat，全部源码和D02脚本已在Implementation提交。权威2051项通过、292个源文件字节与测试hash一致。Preregistration只新增本合同，不修改已验证Python/JS。

## 唯一样本

> 请分五个自然段介绍一个完全离线运行的Markdown目录索引工具，分别说明用途、输入、索引方式、搜索方式和限制。每段后换行。不调用工具，不读取或修改任何文件。

Case D02，单Attempt、全局最多1次物理模型请求；失败、备用、每次HTTP尝试均计数。批次为`~/.mybot-mini/uat/stream-legacy-canary-20261027/`，若存在停止，不删除覆盖。端口127.0.0.1:8900，独立workspace、独立事件SQLite和请求账本、新Session。相同配置路径只读取原本地Provider配置，路径与原字节指纹写私有prepared；不复制凭证文件，不探测远程凭证有效性。

coco/deepseek-v4.1-flash，原Failover配置coco2/glm-5.3-flash保留；但任何第二reservation/HTTP在发送前拒绝。stream=True、stream_options.include_usage=True、web_streaming=True、web_steer=False，SDK retries0。无可调用工具，MCP/Skills/Coding/语义摘要/Judge关闭。单Agent步、输入估算上限14000、输出预留1200、请求超时90秒，未知部署窗口保持UNKNOWN。

## 冻结与执行顺序

Implementation和完整离线/浏览器合成验收已完成。提交本Preregistration并确认干净后：

1. `uv run python -m scripts.stream_legacy_canary.prepare prepare --provider-config <原配置路径> --browser-evidence <本次双Profile探针JSON>`，唯一执行一次。
2. `uv run python -m scripts.stream_legacy_canary.prepare freeze --provider-config <原配置路径>`，唯一执行一次。
3. `uv run python -m scripts.stream_legacy_canary.prepare verify --provider-config <原配置路径>`。
4. Acceptance仅更新文档/脱敏证据，Push后再次verify。不得改源码、重新prepare/freeze或替换数据库。

冻结Preregistration HEAD、完整plan/message/scoring、所有mybot/scripts与pyproject/uv.lock哈希、原配置字节、workspace字节/inode、两库inode、浏览器证据hash。账本必须0 Attempt/0 reservation/0 HTTP；事件库空，Lease可用，端口8900空闲。数据或隔离失败保留证据并停止，不修复冻结来继续。

未来新授权后首先原verify，重新核对进程身份、端口、Lease、冻结/库/账本状态及新鲜0700独立Chrome profile。只启动`uv run python -m scripts.stream_legacy_canary.server --provider-config <原路径> --authorization GRANTED_1_REQUEST`一次，启动即登记唯一Attempt。必须真实DOM新会话、输入上述原文、点击一次。禁止直接写消息API、重发、补充提示、Steer、非流式回退、移除include_usage、为Usage额外请求或付费Judge。原生create_app→Runtime→AgentLoop→ProviderFailover→SDK路径，不绕过工具与Web安全边界。

## 独立评分与证据

- Protocol PASS：真实SDK Chunk、最多8块legacy结构证据、合法终态、自然EOF、SDK close确认、无未解决错误，最终模型文本经原生strip规范化后的hash与SQLite正式助手记录一致。
- Protocol FAIL：非空legacy、结构类型错误、重复finish、终态后语义负载、无EOF、本地解析或其他明确协议异常；保留固定码、Chunk序号、阶段、8块结构、finish观察/接受、EOF/close。字段缺失也不能倒填原值。
- Usage：分别列SDK观察数值与可信结算值；缺可信Usage保持UNKNOWN、不写0、不单独判协议FAIL。完整观察字段不等于可信结算/账单。cost=null直到可信价格可核对。
- UI：同一浏览器performance.now从提交到首次可见文本，确认发生于完成前；SSE宿主emit与浏览器时钟不相减。UI预览不是Protocol PASS。
- Clean Shutdown：实际wait exit0、SDK流关闭、端口释放、Lease释放、SQLite一致。端口消失或cleanup.json内待定退出字段不能替代wait。

失败保留HALT和failed状态，关闭本次已有资源不经过新请求准入门；不清HALT制造成功。先正常SIGINT自己launcher，必要时只对再次核实PID/UID/PPID/启动时间/完整argv/cwd/监听端口不变的自己子服务发SIGINT，有界wait；不强杀、不删锁、不触碰旧服务。无法确认时记录UNKNOWN/清理异常，停止所有后续请求。

## 记录边界

不保存完整Prompt/原始Chunk/模型正文副本、函数名、参数、extra键值、Cookie/CSRF/密钥/Profile或不受控异常字符串。原生私有事件库按正式路径保存回复用于持久性核验，不提交数据库或其正文。SDK observer只保留有界内存文本以计算哈希。截图使用合成样本；未来Live必须遮蔽正文，截图失败不得为取图重新请求。

旧R01/D01资产和真实成绩不改。一次未来D02即使成功也只代表新样本，不保证所有Provider/SDK版本或Steer兼容。新合同与plan.json含义以本次冻结记录为准，后续文档提交不更改冻结源码。
