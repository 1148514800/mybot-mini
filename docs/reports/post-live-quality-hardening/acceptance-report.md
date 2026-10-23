# 真实用户任务质量优化：离线验收

状态：**OFFLINE PASS / BROWSER PASS**。基线58725ca77cfa88ca41f661f1dd343f9f20c1f482，独立分支codex/post-live-quality-hardening。真实模型授权与实际调用均为0；不重跑旧T01/T02/T03，历史结果不改判。

## 改善与可信边界

1. T01只证明该真实单文件案例走通调查→Preview→Receipt Commit→原生测试→当前Revision验证及独立验收，不能外推复杂任务正确率。
2. T02公开测试未覆盖明确负零输出合同，故指定测试通过与独立Task失败同时成立。本轮提供通用合同提示，不硬编码旧答案、不改旧Fixture。
3. Controller verified语义不变。除instruction外，其余方法AST与基线一致；原Patch、Receipt、命令、Failover、Session和权限实现未改。
4. finish_reason=length现在为output_truncated，保留部分文字与用户输入，Web不显示完整成功，CLI与SSE明确不完整；不自动续请求。正常stop文本完成、过滤/空回复/异常/未知分别报告。模型交付结束不等于用户任务正确。
5. v1原文引用仍严格，来源节选与脱敏原始消息双重精确校验；无相似度接受或模型释义替换。协议和默认关闭策略不变。
6. 全条目验证后，可独立确认的非关键有效子集在有合法锚点时部分应用，明确semantic_applied_partial及无效数量；关键约束或假完成证据失效仍fallback，无效引用不进入摘要，不模型重试。
7. 目标/约束与已选决定、未知、未完成、失败类别有保留下限；引用先按真实来源位置排序，避免模型数组倒序导致较新决定被删。仍可能漏选或因空间不足fallback，历史覆盖始终标未验证，原Session保留。
8. 来源逐级缩减并重新经过原TokenCounter，放不下则零发送。没有抬高窗口、主备参数、Controller上限或独立超时，没有绕过物理记账。
9. 没有自动续答或引用失败重试。输入缩减可让原来被阻断的一个摘要请求合法发送，仍在原显式semantic机会内；不宣称更便宜或请求必然减少。
10. CLI/Web分别呈现回复状态、工具失败、Revision指定测试、用户任务正确性未知、历史遗漏、摘要应用/部分/fallback和请求预算不足。新统计无私有正文、Receipt或nonce，权限通道不变。
11. 真实边界识别率、长回复完整性、摘要选择/分类和实际费用是否改善，仍须未来另行预注册与授权。合成比较只能说明机制行为变化。

## 验证范围

新增专项36项通过；最终check_phase 41组1390项，加独立UAT离线补充79项，合计1469项（原1433项全部保留），无跳过。编译与git diff --check通过。详情见offline-validation.json。真实浏览器通过本地合成服务检查截断文字保留、长度限制提示、部分摘要状态及引用统计，并检查正常回复对照；截图见browser-output.jpg、browser-partial.jpg、browser-complete.jpg。浏览器使用内存合成Client，20 Token只是设计的合成Usage，不是供应商账单。

报告同时包含Live根因、输出协议、摘要完整性、Coding合同、新域合成对照、安全审计、剩余风险和后续边界。原私有Live证据仅只读分析；不提交完整私有响应、凭证、Receipt、nonce或主机路径。不合main，不改历史Tag/ZIP。

Implementation Commit：`bc0784920c6978ef642f1ea6efe19fa8176e5dea`。Acceptance 为包含最终验收报告的后续 docs 提交；两者均交付于本独立分支，远程HEAD随Push核对。
