# Decision Provenance & Temporal Validity v1 — OFFLINE PASS

基线ba04931815c222543a7e05bf86147a9a5adb4642，独立分支codex/decision-provenance-temporal-validity。Implementation commit：f1548ca0d309e2ed8bfe348ac750d50f6f95b648。本报告由后续独立Acceptance commit交付；最终远程HEAD在交付回复核对，不在自身文件内伪造自引用SHA。

## 结果与验证

新增56项专项（来源20、时间线20、上下文16）；最终完整check_phase 55组1637项，独立补充79、持久会话预算22、Source-Aware预算28，去重计入1766项，全部PASS、0跳过。1682旧基线+先前独立28+本轮56=1766。定向重复、初次无效运行和浏览器检查不重复计数。compileall、JavaScript语法、git diff --check通过；最终Python/JS源码运行前后哈希一致，详见offline-validation.json。

独立headed Chrome真实点击通过动态双profile Cookie/LocalStorage隔离、两Pin确认、错误模型回答与可信面板区分、替换/撤销、跨七轮保持、服务完整停止及重启恢复。12次均为本地SyntheticClient调用，真实DeepSeek/GLM/摘要/Judge/Provider HTTP全部0，实际供应商Token0、模型费用0。旧余额未使用。两次自身服务exit0、端口与Lease释放、profile清理；旧用户Chrome/8765/私有Live数据未操作。

S03机制：合成错误句“原始笔记永久保留是已确定要求。”原样属于assistant.message；可信集合仅含真实确认的两条原文，没有永久保留Pin。S02机制：旧名[6,12)、新名[12,13)，提交边界有效集合依次旧/新/空，内部序号11拒绝；后来撤销不改变早期状态。见mechanism-evidence.json、synthetic-case-results.md及浏览器截图。

## 十二项设计回答

1. **阻止推断自动成为可信决定**：视图只读真实用户消息和pin确认事件，不消费模型回答、TaskContract或建议；规范化改写没有精确来源就不获确认。classification_proposal永远未验证，且不是工具或写入口。
2. **原用户消息**：未改变。所有展示/上下文变化是临时投影；旧事件、旧Live响应及评分不改。
3. **Schema**：事件Schema仍v1，无新生命周期事件。DB v2新增提交区间索引，因为只看相邻事件无法证明SQLite事务边界。迁移只记录旧库当前边界，不发明旧区间。
4. **历史区间**：Pin添加与终止事件的所属事务提交终点构成左闭右开区间，以sequence为准，不按timestamp/revision；同一事务中间边界不可查。
5. **追溯撤销**：不会。status_at_boundary与current_lifecycle_status分开，旧名在其历史提交边界仍有效；未知旧边界明确拒绝。
6. **Pin与普通原文**：普通原文仅证明用户说过，semantic_classification未分类；固定原文另有真实确认事件和宿主所选用途，不授权更强改写。
7. **建议与推断**：分类词汇与未验证提议区分两者；不以关键词自动分类或确认。助手文本无论自称“已确定”与否，都不产生用户确认权威。
8. **自由文本限制**：未实现通用蕴含检测、实时拦截/纠错或助手影响清除。错误回答可继续出现；可信视图不被污染不等于回答语义正确。
9. **预算开销**：最终样本参考单独保守估算1690–1769 Token，同Pin元数据旧参考1173–1211，增加517–558；不是部署Tokenizer或账单。全部参考进入原输入预算，输出预留不变。
10. **新模型请求**：0。没有新增分类器、语义摘要、隐式Judge或真实Provider连接。
11. **Source Preservation**：原来源跨度遮蔽、独立事实保留、工具配对、预算与观察器兼容检查全部保留并通过。失效Pin正文没有重新无界注入模型；历史详情通过宿主查询。
12. **仍需新DeepSeek验证**：更强义务误判、可选/未决分类、当时有效的自然时态表述、标签复述减少和助手语义残余，均需另行授权的新预注册Live。不能拿本轮机制PASS改判旧Live缺陷。

## 模块、交付与风险

新增agent/decision_provenance.py、storage/decision_timeline.py；集成SessionEventStore、SessionHistory、Context Projection、AgentLoop控制命令、Web runtime/server/static。新增三个专项检查和可复现合成Chrome驱动；生产依赖、Pin写入口、工具权限、TaskContract和TokenCounter不变。

安全内容复核与证据哈希见security-audit.md、security-evidence.json、evidence-hashes.json。无用户会话损失、未知执行或意外文件污染；有意变更仅本分支实现/测试/交接/文档。初次回归因操作员运行中改源码触发冻结门，未当作PASS；最终源码固定后完整重跑通过。旧v1库更早的事务边界不可恢复，升级时须停止同库旧写者；本轮未升级用户或Live旧库。原报告、Tag/ZIP、冻结批次及旧断言全部保留。
