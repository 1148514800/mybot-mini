# AI_HANDOFF

## 当前状态

UAT可靠性离线修复完成：基线a847884568184fcf5317d11ecfd0ec9a721b9db0，本地/远程核对一致；独立分支codex/uat-reliability-remediation，实现提交9f82d36138527105af0260ad71242bb5b9bfd132。原38套件1354+旧UAT13+新增42=1409项通过，compileall/diff通过，真实浏览器HTTP/SSE诊断通过。验收报告docs/reports/uat-reliability-remediation；验收提交为包含本快照的docs提交。按本次授权Push该分支并核对远程HEAD，最终SHA以Git为准。

## 实现与边界

- Fixture v2只新建根先设当前EGID；原check_metadata+dry_run Preview验证真实UID/GID、ACL/xattr/mode、路径/版本/hash，Git、Seatbelt/unittest与预期初始Bug。新prepare冻结前和服务客户端工厂前BLOCKED；U03/U04/U05新APFS预检PASS，原Fixture不动，不执行预检Write。
- 原生Patch仅新增固定白名单码/阶段/意图/建议，解析失败意图unknown。safe_to_retry透传原值；成功Commit无失败建议。不改Receipt/发布/Journal/审批。原生读取路径经RepositoryTool.resolve验证相对路径及范围才展示，MCP不复用。
- 唯一ContextManager按主请求计算available_summary_budget，空间不足零摘要调用；九字段引用v1动态条数、长度、max_tokens上限。先严格验证全部引用，后仅删低优先整项；保护已选goal/constraint，不能适配则明确回退。length单独分类、不额外重试。原Session、Tool ID、权限、Controller/Provider预算不变，CLI/Web状态一致。
- 通用指令区分用户要求/建议/待确认，代码调查考虑search_code、读实现、区分bool类型判断，未知标unknown。仅证明合同送达；真实模型能力未验证。

## 验证与风险

新增预检9、诊断9、自适应14、指令5、合成E2E5项共42通过。完整重测1354项通过；后续长度合同与诊断建议收尾后再次运行所有指定相关专项及旧UAT13项通过。初轮7项safe_to_retry兼容失败已修；旧离线校准1项引用上限过紧已修，原断言未动。完整分母与实际合成数据在报告JSON，不重复累计针对性重跑。

真实DeepSeek/GLM/摘要API/付费Judge均0，真人审批0。原UAT1/6、Coding0/2、摘要0/2及6452Token保持，U05历史根因仍unknown。合法摘要仍可不适配而回退；UTF8估算不是供应商精确保证；真实语义质量、遵循率、Token/费用改善和GLM恢复未验证。

## 下一步与不要重复

离线工程前提已准备；下一次Live须新预注册、新独立Attempt、每个真实Fixture预检PASS与单独预算授权。优先单文件/跨文件Coding闭环和长对话真实摘要。不得重跑旧六例、挪用剩余22次或重判旧结论；不进入新Phase、不合main、不移动历史Tag/ZIP。主目录用户两文件保留。ExFAT确认AppleDouble伪idx移到本机临时可恢复备份，实际Git pack/index未动，后续仍可能生成元数据。
