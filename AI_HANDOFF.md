# AI_HANDOFF

## 当前状态

Streaming & Steer v1工程、专项、完整离线和独立headed Chrome合成验收已通过。分支codex/streaming-steer-v1，基线c2f1baca04dc8b7bc320e9cd9295fe3d5b870331；Implementation f6eb05a75bd710438d026b1b761de3df6ba43a86；验收报告另有独立提交。真实DeepSeek/GLM/摘要/Judge/Provider HTTP均0，旧余额未使用。报告docs/reports/streaming-steer-v1/。

## 实现与边界

新增agent/streaming.py、agent/steer.py，小范围接入原Loop、ProviderFailover、RuntimeAccounting、EventSchema/Store与Web。web.streaming.enabled和web.steer.enabled默认false，旧CLI/非流式兼容。SDK create和consume共用一物理记录；任意首Chunk之后禁止透明Fallback，Usage缺失null。流式工具按index组装并复用严格parse_object，只有可信终态进入原Registry/审批。

Steer绑定真实Session/Turn，单pending、2000字符、32记录，同ID内容幂等；queued不等于applied。未开始工具明确配对跳过，已开始工具不回滚；下一请求重建并通过Token/Controller预算，物理准入才applied。无下一步not_applied，停止discarded，旧Turn/rejected明确响应，审批等待拒绝。原Pin、Decision Provenance、TaskContract及工具权限未变；v1不让Steer修改可信合同或成为永久Pin。

新增steer.queued/resolved为事件schema v2，旧事件v1与DB v2表结构保持；不新增DB迁移。只恢复有界审计，不恢复队列、流、旧审批/Receipt/verified。不同版本写者升级要协调，不能共享不兼容活动库。

SSE使用Turn/Stream ID、序号与有界绝对预览快照，100ms合并和帧渲染；重连状态恢复不重发模型。跨Chunk完整行脱敏，4096字符长行保守隐藏，预览8192字节；文本32768字符、工具65536字符/16调用、deque128。关闭超时3秒或失败维持Lease/不确定阻止。

## 验证

新增97项：流式33、Failover12、Inbox22、Web30。最终check_phase59组1734项，独立补充79、Persistent预算22、Source-Aware预算28，去重1863项全通过、0跳过；重复执行不重复计数。最终Python/JS源码哈希前后一致，compileall、app.js/markdown.js语法、diff检查通过。

Chrome152.0.7977.83/Playwright1.64.1，新0700 profile及双向Cookie/LocalStorage探针通过。真实页面A–G加H停止：终态前中文/Markdown、Steer跳过工具/下一步应用、无后续不应用、断流、真实网络重连、审批拒绝、停止与完整服务重启。最终8次本地SDK Mock HTTP/8流关闭，Steer applied/not_applied/discarded各1；SQLite完整、Pin0、唯一命令被拒且effect=none。自身服务exit0、端口/Lease释放、profile清理，旧8765、用户Chrome、私有Live库未操作。

## 下一步与禁止事项

真实coco/DeepSeek与coco2/GLM流兼容、真实Usage/断线、Steer语义遵从仍UNKNOWN，需另行新预注册和授权，不用旧余额、不重跑历史Live。长行隐私缓冲可能延迟/过度隐藏，非通用秘密语义检测；applied不是模型遵从，输出完成不是任务正确。

旧Source-Aware/Decision阶段语义推断强化和助手影响UNKNOWN仍保留，不因新交互改判历史。不得改旧报告、冻结资产、账本、Phase Tag/ZIP或扩大权限。完成Git交付后不自动进入新Live。
