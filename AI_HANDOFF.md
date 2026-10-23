# AI_HANDOFF

## 当前目标与状态

从指定UAT基线a847884568184fcf5317d11ecfd0ec9a721b9db0创建独立分支codex/uat-reliability-remediation。离线修复已实现，专项及原38套件1354项全量通过，验收汇总进行中；尚未宣称交付完成。不运行Live、不改main/历史Tag/ZIP/旧报告/Fixture，不使用剩余22次。主目录用户两文件保留。

## 实现与决策

- 新Fixture v2仅新建根目录先设当前EGID；预检直接复用原check_metadata及dry_run Preview，检查Git/版本/hash、目录/文件元数据、Seatbelt/unittest与初始Bug；prepare冻结前及服务器客户端工厂前BLOCKED门。旧生成默认语义与原Fixture内容保持。
- 原生Patch新增常量白名单错误码/阶段/意图/建议；解析失败unknown。safe_to_retry仅透传，不改Receipt/发布/Journal/审批。原生读取路径经RepositoryTool.resolve验证才展示相对路径/范围，MCP不复用。
- 唯一ContextManager计算主请求available_summary_budget；不足零摘要调用，九字段引用v1动态条数/长度/max_tokens上限，严格全量验证后仅删低优先整项，保护已选goal/constraint。length单独分类不重试；缓存/Session/权限/Controller原边界不变。Web显示删减、跳过与回退状态。
- 通用指令区分用户要求/建议/待确认；代码调查考虑search_code、读真实实现、区分bool类型判断和未知。只是指令提供验证，真实遵循率unknown。

## 测试与已知边界

新增预检9、诊断9、自适应14、指令5、合成E2E5项共42通过；原压缩22、Patch61、Receipt53及旧UAT13项已通过。初轮check_phase在诊断覆盖旧safe_to_retry处出现7失败，已修成透传且不改原断言，完整重测1354项通过。真实模型API0，浏览器合成失败诊断通过，审批0。

U05历史原因仍unknown；原UAT1/6、Coding0/2和摘要0/2不变。合法摘要仍可能不适配而回退，UTF8估算不是供应商精确保证。真实模型摘要质量、遵循率、Token/费用改善均未验证。报告docs/reports/uat-reliability-remediation已写根因/机制/边界，验收JSON/总报告待最终结果。

## 下一步

完成全量、审计、Implementation与Acceptance两次提交，按本次明确授权Push独立分支并核对远程HEAD。不要重跑旧Live或更改历史资产。两个确认AppleDouble伪idx已移临时可恢复备份；实际Git pack/index未动。
