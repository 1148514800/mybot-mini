# UAT可靠性修复验收

**OFFLINE PASS**。基线 `a847884568184fcf5317d11ecfd0ec9a721b9db0`，分支 `codex/uat-reliability-remediation`，实现提交 `9f82d36138527105af0260ad71242bb5b9bfd132`。验收提交为包含本报告的后续docs提交，可用 `git log -1 --format=%H -- docs/reports/uat-reliability-remediation/acceptance-report.md` 查询。仅离线工程交付，不改判历史UAT。

原38套件 **1354项**、旧UAT离线 **13项**、本轮新增5套件 **42项** 全部通过，合计 **1409项**，无跳过；针对性重复执行不重复累计。compileall与diff检查通过。完整命令、分母、初轮失败及修复后重测见 [offline-validation.json](offline-validation.json)。原测试文件/断言、Judge、Strict评分未改。

1. **U04环境问题能否模型前发现？能。** 新v2 Fixture在文件创建前设置新根当前EGID，原生metadata及Preview实际通过；新prepare冻结前和服务客户端工厂前检查。U03/U04/U05新独立APFS预检全部PASS，文件/Git不变，U04/U05初始Bug确认。见 [Fixture证据](fixture-preflight.json)。
2. **不合规元数据是否仍拒绝？是。** GID不符、真实ACL、真实xattr、symlink、错误hash均保持拒绝；不执行预检Write、不chmod777、不削弱check_metadata。
3. **U05历史错误？仍unknown。** 没有补造其参数、dry_run意图或错误类别，旧六例没有Live补跑。
4. **Web能否显示精确失败原因？已合成验证。** 真实浏览器发送并经真实HTTP/SSE显示unsupported_ownership/preflight/preview及属组建议，最终failed/revision0/修改0/有效测试0；成功Commit另测不显示失败建议。解析失败显示unknown意图，不能假称Preview。
5. **Patch/Receipt泄漏？新增失败事件未发现。** 仅固定白名单，测试确认无失败Patch正文、Receipt或主机绝对路径；MCP不获得本地文件路径展示。原成功Preview的有界脱敏Diff功能保留。见 [诊断与浏览器截图](patch-diagnostics.md)。
6. **调用前能否判断空间不足？能在当前预算策略下判断。** 用主请求真实保留视图、完整schema/plan和输出预留计算available_summary_budget，空间不足0摘要请求；估算不冒充精确供应商Token。
7. **合法摘要仍可能无法应用？可能。** 保护引用太多、模型违反动态合同或空间太小仍回退；不偷偷删除用户约束来声称成功。
8. **能否减少无效摘要调用？合成机制已验证。** 长对话1摘要+1主请求可应用；空间不足只有1主请求、0摘要；同一合法超长文档原样不适配，确定性删低优先引用后适配并保留用户约束。length不重试。见 [实际合成数据](synthetic-comparison.json)。旧Live仍0/2、6452Token，不把两来源算成成功率提升。
9. **哪些模型质量未验证？** 真实摘要语义保真、完整JSON率、需求来源分类、搜索选择、bool解释一致性、Token/费用改善和GLM恢复；指令测试只证明合同送达和预算有效。
10. **下一轮优先？** 新单文件Coding、新跨文件Coding、长对话真实摘要应用与准确性。工程前提已准备；每个新实际Fixture必须重新预检PASS，并使用新预注册、新独立Attempt和单独请求额度授权，不能使用历史22次余额。

真实DeepSeek **0**、GLM **0**、语义API **0**、付费Judge **0**；真人/Live审批 **0**。合成测试使用既有审批fixture，不计真实审批。未Merge main、未动历史Tag/ZIP、未污染主工作区用户修改。

本轮通用Agent指令新增用户要求/可选建议/待确认区分，代码调查考虑search_code并读取实现，区分type/isinstance与bool、未知标unknown；不硬编码CSV答案、不强制普通任务用某工具。CLI/Web共享真实AgentLoop、ContextManager与指令，合成对照状态及输入估算一致。

[根因](root-cause-analysis.md) · [预检](fixture-preflight.md) · [诊断](patch-diagnostics.md) · [压缩](adaptive-compaction.md) · [指令](instruction-quality.md) · [安全审计](security-audit.md) · [风险](remaining-risks.md) · [下轮准备](next-live-readiness.md)。
