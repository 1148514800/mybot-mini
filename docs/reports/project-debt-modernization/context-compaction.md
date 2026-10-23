# 语义压缩与信任边界

调用链：AgentLoop → ContextManager 构造规则视图 → 有旧完整轮次被省略且显式 semantic opt-in → ContextCompactor 构造不带 tools 的摘要请求 → 同一 RuntimeAccounting/Controller/TracedClient/Provider → 校验九字段引用 → 检查主请求预算 → 替换规则摘要。未触发时不增加调用。

九字段：current_goal、confirmed_facts、user_constraints、decisions、completed_work、pending_work、important_artifacts、unresolved_issues、uncertainty。字段内容只是有角色与位置的历史引用；confirmed_facts 名称不使其变成当前可信事实。用户目标/约束只允许用户来源；completed_work 只允许工具来源并拒绝 Error: 开头。助手计划不能通过校验成为完成证据。自称成功但无结构化证据的工具文本仍可能被选中，必须以 Controller 的真实验证为准。

当前选择原文片段而不是自由改写，减少幻觉和失败改写；代价是跨消息推理、遗漏消解与引用语义质量尚未获得真实模型证据。所有来源标记 historical_report_not_current_verification。低信任摘要放 assistant 消息，绝不放 system；历史注入可作为文本存在但不能调用工具、修改权限、恢复 Receipt 或完成 Plan。

每轮1次默认机会（可配置1..2），每次一次逻辑调用、最多主/备两次物理请求；失败也消耗机会。Controller 保留至少一个后续任务请求，全局 Evaluation budget 仍在原 TracedClient gate 处拦截；计数不靠摘要模型自报。输入/输出限额、独立超时、取消传播、非法 JSON/重复键/工具调用/超长输出校验都有专项。额度耗尽后用规则视图；格式/超时等按 on_failure 回退或停止，状态不伪装成功。

缓存只在一次 handle_message 内生存，以完整旧轮次与脱敏集合哈希匹配；来源变化不复用，下一轮重建。有效摘要不写入 Session/SessionStore/磁盘。保留原始历史与工具配对，历史容量仍由原 Session.max_turns 控制。原文先使用已有脱敏函数移除已知主备密钥、凭证样式和64位能力串，再做带不完整标记的来源节选。脱敏启发式不能替代对用户输入敏感信息的管理。

A 长对话、B 长工具结果、C 原生 Preview→Receipt→测试三场景结果在 before-after-comparison.json。这些证明安全边界与合成协议流程，不证明模型能力提升、摘要质量收益或真实 Token 节费。
