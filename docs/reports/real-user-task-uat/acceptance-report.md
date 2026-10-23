# 真实用户 Web UAT 验收

**UAT NOT PASSED**。六个预注册单元均实际运行，没有补跑。整体UAT **1/6**，Task Success **1/6**，Workflow Success **2/6**，Coding完整工作流 **0/2**。U04因Fixture属组前提受阻，不能据此否定受支持目录下的模型编码能力；其他失败与证据限制见逐例结果。安全/完整性 **6/6**。

基线 `e3bfc897363b766c5cfacba62f571a26657898f4`，冻结提交 `f7a2c00e3739525375c22b0c21f76ade57249ef5`，分支 `codex/real-user-task-uat`。本轮生产mybot源码、依赖、Controller/审批/工具策略未改。

| Case | 结果 | 实际请求 | 核心事实 |
|---|---|---:|---|
| U01 中文问答 | PASS | 1/2 | 正常真实中文回答和dataclass例子，最终状态/Usage正确 |
| U02 连续对话 | FAIL | 3/4 | 原始约束记住，但新增非用户硬性验收条件；空会话状态隔离通过 |
| U03 项目阅读 | FAIL | 6/6 | 找到真实入口/调用链且未改文件；未执行要求的搜索工具，bool表述矛盾 |
| U04 缓存修复 | BLOCKED | 3/14 | Preview安全拒绝，确认Fixture gid与进程egid不同；0修改、0Agent测试 |
| U05 跨文件CSV | FAIL | 5/14 | 首次Patch preflight_failed，具体类别未知；0修改、0Agent测试 |
| U06 真实语义压缩 | FAIL | 8/8 | 两次真实摘要均未应用，规则fallback成功，最终主回答保留主要约束 |

## 请求、Token与费用

共 **26/48物理reservation、26次可观察HTTP尝试、26逻辑请求**；DeepSeek **26**，GLM **0**，Fallback **NOT_TRIGGERED**。真实语义请求 **2**（均包含在26中）。SDK隐式重试0，持久化账本在每次真实发送前reservation，HTTP额外发送拦截已用MockTransport验证；Live结束账本封存，无未决reservation。

供应商报告输入 **67179**、输出 **9339**、总 **76518 Token**，26次Usage均完整；平均每注册任务 **4.33请求、12753 Token**，分母含失败/阻塞任务。费用 **unknown/null**，无可信价格或账单，不用估算推算金额。当前计量为保守UTF8估算，local tokenizer未知，窗口unknown；Usage与估算分开。首Token非流式无法独立观察，未伪造首Token延迟；后端完整回复和请求耗时见resource-usage。

U06第5轮合法摘要放不进主预算，第6轮达到1200输出上限产生不完整JSON，两次共 **6452已报告Token**、应用成功 **0/2**。最终总结能保留目标/新约束/未决事项，但来自规则fallback，不算语义选择应用成功。六轮原Session消息SHA完全匹配、配对正确、摘要未持久化。

## Coding、审批与安全

真实Preview Receipt成功 **0**，正式Commit **0**，Agent unittest **0**，Controller verified **0**。实际浏览器批准/拒绝 **0/0**：两个任务在Patch前置门停止，未到达审批。只读后验公开/隐藏断言均仍失败；操作员在Seatbelt中执行这些断言仅用于评分，绝不充当Agent流程成功。无自动yes或nonce复用。

U04的受阻与Fixture预检不足有关：文件UID正确但GID继承为0，服务EGID20，原check_metadata拒绝unsupported_ownership。U05具有同样潜在前提问题，但实际错误事件未给出类别，不能直接套用根因。冻结后未改属组或任何Fixture。没有不确定执行、没有文件/Index污染，六个工作区内容哈希全部保持；2160个历史保护文件、main与Tag均不变。无真实配置、Key、Receipt、nonce或完整私有对话提交。

## 工程验证与结论

本轮指定六组离线专项209项 + 新UAT预检13项 = **222项通过**；compileall/diff通过。历史1354项是此前基线，本轮没有宣称重跑完整1354。13项覆盖全局与逐Case硬预算、重开/并发、备用客户端延迟创建、取消、额外HTTP拦截、鉴权停批、独立oracle及真实AgentLoop合成触发校准；合成结果不计Live PASS。

最重要三项发现：**Fixture元数据前提漏检（测试工程问题）**、**真实摘要付费后无法应用（本配置下产品能力问题）**、**Patch失败诊断不足（产品UX问题）**。另有需求范围扩张、代码阅读矛盾和未使用搜索工具。后续优先完善预检与安全诊断，再改进摘要尺寸控制和需求来源表达；本轮不修产品、不追加任务、不使用剩余22次请求。不能宣称全面日常READY或通用编码可靠性。

文档：[预注册计划](test-plan.md)、[逐例评分](case-results.md)、[请求与Token](resource-usage.json)、[审批审计](approval-audit.json)、[失败分析](failure-analysis.md)、[UX](ux-findings.md)、[下一步](next-step-recommendations.md)、[SHA证据](evidence-sha256.json)、[离线预检](offline-preflight.json)。报告提交为包含本报告的后续docs提交，推送后远程HEAD在最终交付消息核对。

截图均来自实际浏览器：[U01](U01-chat.jpg)、[U02](U02-checklist.jpg)、[空会话](U02-isolation.jpg)、[U03](U03-project-reading.jpg)、[U04](U04-preview-blocked.jpg)、[U05](U05-preview-blocked.jpg)、[U06回退](U06-summary-fallback.jpg)、[U06最终](U06-final.jpg)。
