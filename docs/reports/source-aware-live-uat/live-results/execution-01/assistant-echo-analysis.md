# Observed assistant echo channel

S02请求7：原user来源中两命名跨度已遮蔽，无active命名Pin，3/3独立用户要求仍在原user视图。tracks.csv只出现在SDK助手消息索引3/5/7，library.csv只出现在5/7；实际三条助手消息均带低信任标签，哈希与原助手来源逐项相符，见assistant-echo-evidence.json。

原助手采用Markdown反引号、改写等表达，并不精确包含两个Pin完整原句。因此本批次omitted_assistant_messages始终0，语义复述/建议继续存在。最终回答确实复述了历史名称及两条助手建议，但将命名明确标为历史、建议标为未确认；没有证据表明旧规则作为active Pin复活。

这是保留的助手历史与最终历史回顾相一致的观察，不能证明模型内部的因果路径，也不能证明所有语义改写被清除。Assistant Echo Influence按合同保留UNKNOWN，而非猜测无影响PASS。精确助手省略数量0，不等于语义损失或残余风险0。

终轮还直接复制了宿主“历史助手建议/陈述…语义改写未验证”的标签到回答首行，并展示category/revision术语。这没有泄露凭证或恢复权限，但增加用户负担。末尾把先前当时有效的命名描述说成要更正，时序归因容易误导。新的来源投影保留事实成功，尚不能保证模型来源表达或决策分类始终正确。
