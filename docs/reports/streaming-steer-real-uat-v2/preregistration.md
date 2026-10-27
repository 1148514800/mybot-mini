# Streaming Tool Call & Steer v2 — frozen contract

LIVE_AUTHORIZATION: NOT_GRANTED

基线54eeeb80be0cdef65f25affc6eae6c907474cb19；独立分支codex/streaming-steer-real-uat-v2。本轮只有离线准备，真实模型0。未来必须新收到精确GRANTED_6_REQUESTS；旧D02的1次授权已耗尽，R01/D01/D02均不重放、不改判、不读取旧私有账本或回复。

新唯一批次：`~/.mybot-mini/uat/streaming-steer-real-v2-20261026/`，存在则停止，不删除或覆盖。独立workspace、事件SQLite、请求SQLite，端口127.0.0.1:8901；原Provider配置路径由唯一prepared记录，不复制凭证。coco/deepseek-v4.1-flash，原coco2/glm-5.3-flash策略保持；主备、失败、每个HTTP都计入总6。Case顺序T01→T02→T03，额度4/1/1，每Case唯一Attempt，不转移余量、不自动重跑。

## Frozen messages and actions

T01（最多4次）：

> 请先列出当前目录，再读取README.md，根据文件内容说明这个项目的用途。只允许使用list_files和read_file，不修改任何文件。请根据真实读取结果回答，不要猜测。

首个真实非终态Chunk交付给consumer，且consumer再次请求iterator后，Chrome真实提交：

> 调整执行顺序：优先读取README.md，不要读取其他示例文件。确认README内容后，用两句话说明项目用途，并包含README中的项目标识。不要修改文件。

T02（最多1次，新Session）：

> 请用四句话解释Python列表推导式。不要调用工具。

首个真实非终态交付后，Chrome真实提交：

> 改为英文回答。

T03（最多1次，新Session）：

> 请写一份较长的中文Markdown说明，分八个章节介绍完全离线的Markdown目录检索工具，依次说明目标、输入、索引、查询、排序、结果展示、错误处理与限制，每章给出解释和示例并分行展示。只做概念说明，不调用工具，不读取、修改或删除任何文件。

首个真实非终态交付后，Chrome点击Stop一次。首Chunk可以只有role/合法工具片段；不要求制造可见文字来延长窗口。

T01/T03只在本Case首个真正收到Chunk的SDK流中使用8秒屏障：先原样yield首个非终态Chunk，consumer恢复iterator后才等待。后续流无屏障，T02无人工屏障。取消可提前中断8秒，记录实际等待。首块终态时不伪造窗口；动作前任务已结束则INCONCLUSIVE/BLOCKED，已发生请求计入预算，不重试。所有屏障时间独立记录，不伪称自然Provider延迟。

Fixture README.md为：纯本地Markdown搜索工具、不使用外部网络、只读取本地Markdown文档、公开标识RIVER-READONLY-73。两个普通示例examples/alpha.md、examples/beta.md含公开示例。完整字节由plan.FIXTURES冻结。T01工具只list_files/read_file，T02/T03空Registry；原生规划工具注册被UAT局部只读Registry省略，不替换AgentLoop或工具。stream/include_usage开启，Steer开启但服务只允许冻结Case操作；MCP/Skills/Coding/摘要/Judge关闭、SDK retries0。输入估算上限14000、输出预留1200、max_react_steps4、请求超时90秒及原Failover时间切分不改。

## Independent acceptance

T01按四层分别评分：

1. 接收：正确Turn ID、唯一DOM提交、原文匹配、事件source=user、queued，初始在途SDK请求hash未变。
2. 工具：真实SDK tool_calls逐块组装、可信tool_calls终态、未执行调用有明确executed=false且按批次ID合法配对；不完整JSON不得执行。真实执行与跳过分别记录，不虚构历史。
3. 下一请求：原生on_dispatch准入、持久reservation、真实HTTP、SDK响应各有独立证据；实际请求中精确Steer原文及来源事件匹配。UI applied由准入触发，不证明HTTP或远端理解。
4. 行为：补充后优先真实读取README、不得先读示例，真实工具结果带项目标识、最终两句话反映用途且包含标识，无编造执行。形状/标识布尔检查仅是辅助，真实语义由操作员独立评审；不能由字符串命中自动判完整Semantic PASS。不用付费Judge。

直接答复/无工具/无下一步如实记录Tool Workflow与场景前提未满足，不追加提问。普通语义/时序前提失败无安全阻断时可继续后续Case，独立Case ledger completed只代表该Attempt结束，不等于Task Success。

T02：排队后无下一模型步骤必须not_applied，UI清晰，原请求不变、总1次，无自动补发；若动作太晚不伪造排队。刷新/原生SSE重连只读，不重发模型。

T03：正在真实流中Stop、SDK close确认、不可信部分不写成complete、不执行未完成工具、Usage无法确认则null、无Fallback/retry、资源释放且无execution_uncertain。取消是预期未完成，不当作可信自然EOF。

任何新协议拒绝、权限/预算/存储/不确定执行异常HALT后续依赖Case，保留码/阶段/序号/最多8块结构。无HALT的语义失败按原标准FAIL并继续。HALT不阻止原生清理自己已有资源，不清HALT制造成功。

## Freeze, browser and cleanup

全部UAT源码和本合同提交、工作树干净后唯一prepare→freeze→verify。冻结292个既有源文件及新脚本、配置原字节、完整消息/Fixture/评分/预算/端口、workspace指纹/inode、两库inode和隔离证据。Acceptance只更新文档，Push核对远程HEAD后再次verify。禁止后改源码、替换库、再prepare/freeze。

离线SDK均MockTransport；新0700 headed Chrome先双profile同Origin Cookie/LocalStorage双向隔离，再用第三profile运行实际原生Web合成。Live将另建新profile，并重新核对冻结/账本、进程/端口、Lease和隔离。不得操作用户Chrome、8765或共享Git AppleDouble旁文件。

未来授权后原verify及环境检查通过，使用`uv run python -m scripts.streaming_steer_real_uat_v2.server --case T01 --provider-config <原路径> --authorization GRANTED_6_REQUESTS`，T02/T03相同入口按序在上一Case关闭结算后启动。冻结browser.py默认MOCK；--live只接受精确新授权，操作员仍须先重新完成双profile与环境只读预检。

所有聊天/Steer/Stop由真实DOM操作，不使用curl或直接API写。安全关闭只SIGINT自己的launcher，必要时再次核对PID/UID/PPID/出生时间/完整argv/cwd/监听口相同的子服务再SIGINT；有界wait，不能SIGKILL/pkill/删锁。Cleanup PASS必须wait exit0、SDK close、端口释放、Lease释放、SQLite一致和自有Chrome/profile清理，不能只凭端口消失。

## Evidence privacy and counts

报告只写受控原文比较布尔、Source ID/sequence/hash、请求和工具结果hash、工具许可枚举/Fixture分类（不写原参数）、分块安全结构和数值Usage。完整Prompt/原始Chunk/私有回复/参数/密钥/Cookie/CSRF/nonce/Profile/SQLite不提交。原生私有事件库保留可信用户来源和正式回复，不导出正文。

分别统计logical_requests、physical_reservations、actual_http_attempts、provider/model、fallback_dispatch、Chunk/可信终态、observed_usage与settled_usage、cost。新观察器在native终态校验结束后的下一SDK入口或Turn结算才结算已关闭流；EOF也不单独使Usage可信。价格/账单未核对则cost=null。RuntimeAccounting内部准入记录不替代reservation或HTTP实数。
