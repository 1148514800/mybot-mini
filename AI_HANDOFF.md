# AI_HANDOFF

## 当前目标与状态

Source-Aware Context Projection工程实现已完成，分支codex/source-aware-context-projection，基线e9f2e822。原Live L01/L02/L03及3/累计5来源损失结论不改；原私有DB/账本/冻结资产未访问或变更。本轮真实DeepSeek/GLM/摘要/Judge请求均0。

## 实现

HistoryTurn在消息dict外保留session/source ID，SQLite恢复取持久ID；SessionHistory→context_projection精确验证user来源与Unicode span，copy中只遮蔽失效跨度、保留原文独立片段。工具组无法安全细分、来源缺失/正文截断/脱敏等情况保守省略并计数。历史助手精确复述省略，其他改写标历史/非权威/未验证；生命周期参考包含active集合及失效状态，不授予权限。同category不再自动needs_review，显示multiple_same_category/unassessed。

先安全投影再预算/摘要；局部遮蔽进入CLI/Web同一context诊断，不能显示历史完整。EventStore/schema/TaskContract/Tool Authority未重构，原生产依赖不变。

## 验证与资料

新增21+12+9=42专项已通过，已接入check_phase。旧提交独立git archive+真实AgentLoop/SyntheticClient对照：原替换损失3、撤销累计5；新两阶段保留5/5，原SQLite消息不变。headed独立Playwright Chrome合成A–E通过（兼容Pin、替换、撤销、重启、工具协议），自己的服务/profile已清理。

已通过全量52组1581项及79补充；因旧整轮相等损失计数不适用局部遮蔽，预算门离线E2E增加原基线3/5+新请求5/5断言（未改冻结消息/observer/评分），22项已重新通过。最终源树哈希稳定复核通过：52组1581+79补充+22预算门=1682去重项，0失败/skip；compileall、JS语法、diff检查通过。Acceptance提交记录最终证据。学习专题docs/phases/source-aware-context-projection.md，不编号、不创建/更改历史Tag或ZIP。报告docs/reports/source-aware-context-projection/。

## 后续边界

未知助手语义改写不能可靠清除；协议组/来源失败/预算仍会导致明确的信息损失。离线机制改善不等于DeepSeek真实回答改善。旧冻结observer information_loss按整轮对象相等比较，在局部投影后会把保留事实误计为丢失，后续新合同须用新诊断/实际user单元核查；本轮不改原observer。不要运行原Live批次或使用剩余2次额度。Implementation 892a1c31353cdd1b342a9c195d8d646efa5b0e7e；Acceptance为随后报告提交，Push并核对远程HEAD，不合main。
