# AI_HANDOFF

## 当前状态

Source-Aware真实语义UAT只获NOT_GRANTED，禁止调用真实DeepSeek/GLM/摘要/Judge或旧余额。新分支codex/source-aware-live-uat，基线d310a06d533cc258067a487e12adc8f6f5f6fc45。生产mybot/、依赖、旧Harness/报告/私有数据库不改。原1682项工程验收及旧Live结论保留。

## 本轮离线预注册

scripts/source_aware_uat固定S01照片3条、S02音乐4条、S03阅读笔记2条，预算4/4/2，全局10，每Case一次Attempt。新独立ledger复用schema/HTTP/SDK gate，任何未结算阻止后续；新授权精确GRANTED_10_REQUESTS且先于凭证/SDK。仅新隔离薄适配器，不修改生产Harness。

evidence以真实Source ID/Session/user/span核对实际SDK user视图，助手复述不计来源保留，局部遮蔽/预算/协议与语义未知分开。S01五要求、S02三要求、S03两约束+可选建议+未决状态。历史命名被全部遮蔽时，模型诚实UNKNOWN不记安全失败，也不记完整Task PASS。

28项新Mock门及九条原文正式Runtime流程通过；独立headed Chrome同Origin Cookie/LocalStorage双向隔离通过，两个临时profile/服务清理。新批次计划~/.mybot-mini/uat/source-aware-live-20261025，须在Preregistration提交后仅prepare/freeze一次，Acceptance记录实际哈希/inode和零账本。生产Provider配置原路径只读指纹，远端有效性未验证。实际真实模型请求0。

## 下一步与禁止事项

完成本次唯一离线prepare/freeze、Acceptance报告和Push核对后停止；未来必须新的人类GRANTED_10_REQUESTS授权才能按S01→S02→S03执行原冻结计划。冻结后只verify，不重新prepare/freeze、新建替代账本、改消息/跨度/评分或追加提示。新资源与用户8765/Chrome隔离，不能触碰旧私有DB或用户内存会话。报告docs/reports/source-aware-live-uat/；学习专题docs/phases/source-aware-live-uat.md，不创建历史Tag/ZIP。
