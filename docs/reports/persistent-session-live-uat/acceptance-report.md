# 持久会话与Pinned Context真实UAT：离线准备交付

**OFFLINE PREPARATION PASS / LIVE BLOCKED**。

LIVE_AUTHORIZATION: NOT_GRANTED。按用户授权门完成预注册、离线预算测试、环境预检和干净提交冻结后停止；没有启动真实模型、没有实际Case Attempt，没有用合成成绩冒充真实成功。

基线：75cfcd6e1e04ab4d755aa2edf541a08dfedc9da7。分支：codex/persistent-session-live-uat。Preregistration SHA：`86105406ed46c32024a4c8d7d669eaaf6ca0be10`。本报告所在后续docs提交为Acceptance，最终SHA/远程HEAD在交付消息核对。

## 用户问题与真实结果

| 问题 | 结论 |
|---|---|
| 是否获得Live授权？ | 否，NOT_GRANTED。没有请求或推定授权。 |
| L01/L02/L03结果？ | 三项均BLOCKED、0 Attempt，不是FAIL或PASS。 |
| DeepSeek是否使用早期Pin？ | 未验证，没有真实DeepSeek请求。 |
| 超过六轮后是否遵守约束？ | 真实语义遵从未知；仅SDK MockTransport机制预检通过。 |
| 替换/撤销是否正确？ | 真实UAT未执行；离线真实Web Runtime/AgentLoop/SQLite数据流及原专项通过，不据此宣称模型遵从。 |
| 是否有无关历史损失？ | 离线L02第三轮省略3个已标注无关用户产品单元，第四轮累计5个；真实值/助手语义损失待评估，这是已知下界。 |
| Web重启能继续吗？ | 原基线及本次ASGI/SQLite重开机制预检通过；真实浏览器+DeepSeek L03尚未运行。 |
| 实际请求次数/16？ | 0/16，primary0、backup0、HTTP发送0、摘要0；真实账本reservation0/case0。 |
| 真实供应商Token？ | 输入0、输出0，无请求。没有伪造输入估算或首Token时间。 |
| 费用可确认吗？ | cost=null；无可信单价，16次不是美元硬上限。 |
| 不确定执行或数据污染？ | 本轮没有Live执行；准备workspace指纹不变、DB无聊天。没有改真实配置/用户项目/生产源码。 |
| 下阶段最值得修复什么？ | 先获新授权完成真实验证；具体产品风险为撤销/替换整轮裁剪连带省略无关信息，应在新任务中研究保留来源/协议完整的更细粒度投影。 |

## 已完成准备

- 冻结L01九条、L02四条、L03一条自然输入、实际浏览器Pin操作顺序、Unicode跨度、来源消息hash/轮次、独立评分规则、停止条件、路径和配置。L01后续不原样重复最早两条Pin；L03复用L01 session，L02用独立session。
- 预算10/4/2、全局16，单Attempt、不转移额度、不重跑。复用既有UAT SQLite账本/HTTP gate/SDK adapter，新增本批次隔离；原SDK max_retries=0，意外摘要先记保守reservation再停止。进程重启不能归零，未结算request阻止新Case。代码与配置在reserve及HTTP前重验。
- 原真实create_app/ChatRuntime/AgentLoop由新测试factory接入，生产mybot未修改。只读可丢弃workspace、event_sqlite/max_turns6、关闭MCP与语义摘要；估算输入14000、输出1800、请求90秒。主DeepSeek/备GLM型号从本地真实配置核对，远程有效性未验证。
- 新预算/adapter22项测试通过；11个相关专项合计236项通过，含原EventStore22、Recovery18、WebPersistence24、Pinned17、Projection10、TokenBudget16、ProviderFailover17、Web53、旧UAT13、v2 24。见offline-preflight.json精确数量和日志hash。原1618基线文件保持，不声称本轮重新跑过全部1618。
- MockTransport完整数据流14次只在临时合成测试中；真实私有批次账本仍0。真实浏览器Live尚未获授权，不生成、复用或伪造截图。
- compileall、git diff --check通过。997原跟踪文件除交接外保持，834个保护路径未变，无秘密或真实数据库提交。独立分支双提交后Push，保留main用户改动。

## 冻结证据与停止位置

私有freeze.json绑定预注册提交、plan/source/配置/workspace指纹及event/ledger inode；报告提交仅为其后代。公开指纹在offline-preflight.json，精确私有路径/原始配置不提交Git。Prepared空数据库大小86016字节只是初始化存储，不是Live事件增长。已有历史Pin机制局限保持，不为追求PASS修改源码。

只有新的明确GRANTED_16_REQUESTS，且全部冻结/凭证/账本/进程/lease检查通过，才可按预注册顺序运行。当前在此停止，不自动启动Live、不复用旧额度。详见preregistration.md、case-results.md、information-loss-analysis.md、security-audit.md及三个JSON证据文件。
