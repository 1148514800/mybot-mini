# 自适应语义压缩

复用唯一 ContextManager、TokenCounter、ContextCompactor。AgentLoop先从原规则视图中去掉可替换的规则摘要，保留完整System、当前用户及工具配对、Plan、完整Tool Schema、保留的近期历史。ContextManager.summary_budget 计算插入空摘要消息后的 JSON/消息结构开销，并通过原 TokenCounter.inspect 的输入限制和模型窗口减输出预留，得到 available_summary_budget；字符兼容模式保持字符语义。估算模式使用保守UTF8计量，不是供应商精确Token保证。

调用前要求有低信任标签、九字段空结构和至少一个带来源引用的保守空间（额外200单位结构预留）。不足直接 semantic_skipped_insufficient_room，原规则摘要/省略标记保留，摘要模型零请求。不增加max_calls，Controller请求预留、Provider预算、取消和独立超时仍原路执行。

九字段引用v1保持兼容；新增第二条System合同提供动态总引用条数、每条引用字符上限（最多500）和 max_tokens（最多原配置output_tokens）。输入来源仍是已脱敏的历史节选，不含工具权限；标签和source_role/evidence_status开销纳入应用检查。模型输出另有限定字节上限（动态max_tokens×8，属于本地防护而非精确Token证明）。

响应先完整严格验证每个字段、条目、来源、角色与原文子串，包括后来可能被删的条目。length→fallback_output_truncated；超时→fallback_timeout；非法格式/引用沿用兼容状态fallback_invalid_or_failed_response。禁止额外重试。合法响应只执行一次有界的确定性删项流程：先删超出合同的低优先引用，再按artifact/fact/completed/issue/decision/pending/uncertainty顺序删除整项直到实际主请求可容纳，不改写任何引用。current_goal和user_constraints不为适配而删减，不能保留就回退并明确可能遗漏。所有数组仍符合已验证v1结构；原Session不改、Tool ID配对不改，摘要不持久化，也不授权完成状态。

状态区分 semantic_applied、semantic_applied_pruned、semantic_skipped_insufficient_room、fallback_output_truncated、fallback_timeout及原兼容fallback。Web针对删减、空间不足和length提供不同提示，CLI输出同一stats状态。合法摘要仍可能无法应用：保护事实过多、模型违反合同或剩余空间很小都会回退；规划只减少可预见无效调用，不能保证真实模型一定输出有效JSON或正确语义。

实测对照见 synthetic-comparison.json：真实AgentLoop合成长对话可应用；空间不足仅1次主模型合成调用、0次摘要；同一合法过长引用文档原样不适配，删低优先条目后适配并保留用户约束。历史Live0/2不变，不计算跨来源的成功率提升或真实节费。

```bash
uv run python -m scripts.check_adaptive_compaction
uv run python -m scripts.check_context_compaction
uv run python -m scripts.check_token_budget
uv run python -m scripts.check_remediation_e2e --comparison docs/reports/uat-reliability-remediation/synthetic-comparison.json
```
