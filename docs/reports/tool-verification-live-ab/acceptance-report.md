# 新样本真实 A/B 验收

**OFFLINE PASS / LIVE INFRA PASS；严格成功率提升未得到证明。** 全部8个预注册Attempt完成、没有补跑。Baseline与Candidate均Strict 3/4；一对Candidate胜、一对Baseline胜、两对打平。本轮不是全部任务通过，不据4个任务对推断总体成功率或生产稳定性。

用户授权总128次物理请求、接受费用未知；实际逻辑/物理/真实HTTP均60，剩余68不用作新Attempt。全部请求返回，实际可观察Token281412（输入268162、输出13250），Usage完整；价格未知，费用null。真实PTY独立yes批准8次、拒绝0、挑战复用0。没有额外模型请求、付费Judge或强制故障注入。

| 指标 | Baseline | Candidate |
| --- | --- | --- |
| 计划 / 实际Attempt | 4 / 4 | 4 / 4 |
| Strict / Controller verified / Hidden Pass | 3 / 3 / 3 | 3 / 3 / 3 |
| 逻辑 / 物理 / 真实HTTP | 32 / 32 / 32 | 28 / 28 / 28 |
| 工具调用 | 43 | 43 |
| Patch invalid_arguments | 2 | 1 |
| stale Preview | 1 | 0 |
| 提交Patch | 3 | 3 |
| 可观察输入 / 输出Token | 136838 / 7224 | 131324 / 6026 |
| Schema字符累计 | 225120 | 206220 |

Candidate少4次请求，其中3次差额出现在首例Candidate提前失败（4次，对Baseline成功7次）。因此不能把聚合请求或Token较少解读为同质量效率提升。两组都严格通过的两对任务中，请求仅为Baseline17、Candidate16；仍不足以外推。参数错误和stale计数较少也只属于本轮观察，没有总体错误率结论。

## 每对真实结果

| 新任务 | Baseline | Candidate | 基于脱敏证据的说明 |
| --- | --- | --- | --- |
| bucket-boundaries-v1 | Strict Pass，7请求 | Strict Fail，4请求 | Candidate成功Preview后，后续Patch在argument_parsing报invalid_arguments，safe_to_retry=false，未提交；意图/非法字段unknown |
| quoted-cells-v1 | Strict Pass，8请求 | Strict Pass，7请求 | Baseline一次stale Preview，后续模型显式操作取得有效Patch/测试；没有客户端自动重放 |
| reservation-flow-v1 | Strict Fail，8请求 | Strict Pass，8请求 | Baseline一次可纠正Preview validation错误，随后Preview成功，但正式Write validation错误不可安全恢复，未提交 |
| span-coverage-v1 | Strict Pass，9请求 | Strict Pass，9请求 | Candidate两次unittest成功：第一次在Patch前、不构成当前修复证据；第二次在Patch后，Controller和Trace认可Revision1 |

完整逐例来源、原failure与统一coding-failure-v2解释见comparison.json；原raw不改判。2个失败均blocked / patch_failed_without_safe_recovery，保留计划分母，未自动重试Write或放宽解析恢复。Trace在参数无法解析时会默认标记patch_preview=true，这不是可确认的Preview意图，分析没有据此推断dry_run或具体原始参数。

## 冻结与安全

- Baseline：`871510f8a682990da63448ef27ec282c376a8711`；Candidate：`04b6968fdab288d8562447e25c84a6d5cec3df41`。
- 实验实现/预注册冻结：`553de2d39d0ddab8e54cce79ba69af1db83dfb58`。实验源码、任务、公开/私有测试、参考和评分在Live期间未修改。
- 共享驱动分别在两个干净APFS worktree的新Python进程中运行原Harness；无monkeypatch、额外提示、工具执行器或评分替换。两组自然failover、配置字节、128/16物理预算、16逻辑预算及90/480/600秒、2048输出相同。
- 所有60次调用为coco / deepseek-v4.1-flash；GLM备用调用0、自然fallback0。不能据此声称GLM或自然故障切换能力得到真实验证。固定的是请求模型别名，供应商不可变后端版本不可核验。
- 全部8个Attempt确认清理，工具ID配对、Journal/Index/保护文件、审批、Seatbelt审计通过；不确定/取消/超时/权限异常0；重复动作指标均0。原生run_command全部逐次实际TTY核准，没有缓存yes。
- 全局60条发送前reservation及60条结果，与8个raw/terminal/finished逐项交叉验证。154份脱敏证据副本及SHA256清单随报告保存；原Campaign证据只读保留。
- 583项旧保护文件、旧13例及历史Canary/Phase25/前轮闭环报告、main、26个Tag、53个ZIP和原配置哈希保持。未进入Phase26、未合并main或重导出ZIP。

整体grading_code_sha256包含被比较的benchmark/metrics，因此两组完整指纹不同；真正Judge、fixture加载、live预算和Strict规则文件逐字节一致，见preflight-comparison.json。新私有测试由本轮作者在Live前编写，模型不可访问；任务是新构造的自包含Benchmark，并非自然采集的生产仓库问题，也不构成对设计者盲测。

## 离线与交付

新增专项29/29；完整1187/1187、33套件、零跳过，原1158项保留；编译/diff通过。离线预检两组均验证全部4个新任务有效，记录见offline-validation.json。Live后只增加报告与交接，不修改已验证的实验源码。

证据入口：comparison.json、evidence-inventory.json、evidence/、security-audit.json、failure-analysis.md、next-phase-readiness.md、preregistration.md。原运行目录为忽略的runs/tool_verification_ab/campaign-v1，已存在目录拒绝重放。验收提交是包含本报告的文档提交，精确SHA用git log查询；交付推送独立分支codex/tool-verification-live-ab并核对远端HEAD。

结论：原安全与验证门在这8例真实执行中保持；参数预防仍不能消除Patch输入失败。没有自动宣布修复、没有用Hidden Pass替代合法结束、没有消耗剩余额度“补好”失败。下一步可研究有限的解析错误诊断，但任何改进都应离线另行冻结，不得基于这4例私有断言调参后再称未见，也不自动开启新Live。
