# Security and privacy audit

- 新分支严格从e9f2e822创建独立APFS worktree；不合并main。主checkout的两处用户未提交修改不触碰。
- 不访问原Live私有SQLite，不启动persistent_uat.server，不读取或变更原Provider配置、冻结目录、账本、Preregistration、历史报告、Tag或ZIP。公共历史报告/冻结脚本的Git差异为零；原私有资产不通过本轮读取或重放来“验证”。
- 实验只用新临时SQLite、workspace与公开产品单元。baseline使用git archive导出原提交到新临时目录、同一无凭证SyntheticClient运行；没有读取原模型私有回复。预算专项自身的prepare/freeze只作用于其原有私有临时fixture，非原Live批次，HTTP均MockTransport。
- 源历史与Pin事件不覆写、不删除、不迁移schema。来源校验与scope在宿主执行，模型没有Pin Tool，不可自授系统/工具权限。历史工具/审批/Receipt/verified不会恢复。
- 生命周期参考为有界user-role宿主元数据；不嵌入失效Pin正文、凭证或审批。SSE新增诊断仅统计数值与固定reason code。投影在copy上运行，消息dict没有额外API字段，内部ID不靠文本猜测。
- 工具协议有明确完整组回退；TokenCounter、输出保留、provider窗口、原请求账本/Controller门不绕过。不新增LLM分类/冲突检测/摘要触发路径。DeepSeek、GLM、真实摘要、付费Judge均0，原Live余额不使用。
- 测试没有删除或减少。两处行为迁移：同category冲突标记断言改为中性且两Pin保持有效；旧预算E2E保留3/5原基线断言，并新增实际请求5/5与局部遮蔽断言。冻结observer的整轮相等计数在局部遮蔽后不适用，明确记录其5/5误报，不修改旧Live评分或observer源码。
- 截图仅合成内容，无API Key、Cookie、CSRF、Receipt或原用户聊天。临时Chrome profile和自己的服务已关闭清理。提交不含SQLite、profile、完整请求Prompt或私有调试日志；日志仅存SHA与结果元数据。

源树前后哈希、各回归日志哈希、保护路径审查与证据索引见offline-validation.json及security-evidence.json。系统/同UID恶意进程、模型真实语义遵从不由本轮离线实验证明。
