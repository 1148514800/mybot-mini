# Streaming & Steer真实Provider UAT预注册

LIVE_AUTHORIZATION: NOT_GRANTED。只有未来人类明确GRANTED_8_REQUESTS并重新通过动态核验才可开始；旧授权与余额不可复用。当前仅离线准备，全部真实Case未执行。

基线3a8a3d67d7305bb55a357b8a851dde0446fc2c4f；独立分支codex/streaming-steer-live-uat。完整用户消息、Steer、Fixture、评分、顺序和停止规则以frozen-plan.json及scripts.streaming_steer_uat.plan.contract为准，plan SHA256：0adcfdce78b7be5dbf5fca7da1f1583f90f2439b2c9081c76cc3fccfc11c08cd.

## 固定执行与额度

R01→R02→R03→R04，各只有一个Attempt；额度1/4/1/2，全局8，不转移、不补跑。包含主/备用、失败及取消发送；Ledger预留在SDK与HTTP之前持久提交，贯穿全部流消费与关闭，未结算阻止继续。摘要/判官禁用、SDK retries=0。

R01新会话发送五段本地Markdown搜索说明请求，禁止工具；分别评分原生流、可信终态、最终文本与SDK组装一致、首段终态前可见和无额外请求。R02新会话发送先看目录/读README原文；在首个真实非终态Chunk之后经Web提交固定Steer。分别判队列接收、未执行工具配对跳过与下一请求准入、真实读取顺序/最终两句使用LANTERN-LOCAL-42。模型不调用工具或无后续步骤是FAIL/not_applied，不能诱导重试。R03四行Python列表推导式说明，首Chunk后经Web补充英文要求；无下一步必须not_applied、仅一请求。R04最后执行较长Markdown解释，首Chunk后经Web点击停止；核验关闭、部分输出/工具不冒充完成、Usage未知、无重发及Lease清理。

R01无屏障；R02/R03/R04每条物理流在首个真实非终态Chunk原样yield后等待8秒，再按原顺序消费。首Chunk已终态则不等待，场景前提未满足据实BLOCKED，不重跑。屏障不改模型内容/Tool Call，不伪造首Chunk或可见Token，也不能把8秒当自然延迟。

## 安全及正式入口

独立8899端口、0700新Chrome身份、独立SQLite及可抛弃workspace；没有操作8765、用户Chrome或旧私有Live库。完整create_app→ChatRuntime→原AgentLoop→ProviderFailover→SDK路径。真实消息、Steer和停止仅通过真实页面。

R02唯一可用Registry项read_file/list_files；其他Case无可调用工具。由于原Loop自动注册计划元数据工具，UAT进程在自己的ASGI lifespan内通过受限Registry工厂额外收紧注册，退出还原；不替换AgentLoop，不包装原生读取工具，不更改生产文件/权限。所有请求工具schema再经SDK适配器白名单检查。此操作员环境差异明确冻结，不声称与普通Web逐字相同。

Steer必须符合原文、当前Turn和真实首Chunk前提；意外提前终态或无法及时操作只能记录未满足，不伪装成功。紧急停止会中止批次，不伪装R04通过。权限/计数/冻结/凭证/完整性/清理异常立即停止全部；stream或stream_options拒绝停止依赖场景。普通语义失败保留FAIL并按合同继续，禁止改提示、关stream_options或换非流式求PASS。

## 时间、来源与评分

SDK准入、HTTP、首Chunk、首文本与SSE首次预览发出可用同服务进程monotonic；记录预览前Chunk数及实际受控等待。浏览器提交到DOM可见在操作员进程另测，并记录轮询误差。SDK开始到浏览器DOM的跨进程差没有可信关联时UNKNOWN；SSE发出时间不冒充DOM可见，空role Chunk不冒充文本Token。

十个独立维度为Protocol Compatibility、Streaming Integrity、Workflow Success、Tool Safety、Steer Queue Correctness、Steer Application、Model Semantic Adherence、UI Responsiveness、Resource Accounting、Cleanup Integrity。协议成功不等于实时UX，queued不等于applied，applied不等于语义遵从。无可靠Usage为null，无可靠价格cost=null；真实取消后远端Token/计费不可确认则UNKNOWN。

## 唯一prepare/freeze

新批次~/.mybot-mini/uat/streaming-steer-live-20261026/，已唯一prepare，未发送请求。原Provider路径只存私有prepared.json，不提交凭证。预注册提交完成且工作树干净后仅执行一次freeze，再verify；冻结源码/配置字节、端点指纹、Fixture、数据库inode和评分。严禁重建账本或重新prepare/freeze以修复执行问题。后续只接受新授权与动态预检，不自动执行。
