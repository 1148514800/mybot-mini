# Tool Reliability & Verification Closure

**OFFLINE PASS**。新增专项44/44；干净基线1114/1114（31套件），最终全量1158/1158（32套件），零跳过。所有要求的独立回归、编译、diff与保护/凭证审查通过。真实模型HTTP0，付费Judge0，Codex真实yes审核0。

- Implementation：`04b6968fdab288d8562447e25c84a6d5cec3df41`。
- Acceptance：包含本报告及同行验收JSON的独立文档提交；精确SHA由`git log -1 --format=%H -- docs/reports/tool-verification-reliability/acceptance-report.md`查询（不在提交内自引用其尚未生成的SHA）。
- 分支：`codex/tool-verification-reliability`，交付Push到origin同名分支并核对HEAD。
- 保持569项基线保护文件、13个原Attempt raw、main、全部26个Tag及53个ZIP原值；不是Phase26，不合并main，不重新归档。
- 下一阶段工程READY；真实A/B尚未验证，执行仍需独立新授权。

| 独立入口 | 通过数 |
| --- | --- |
| check_tool_verification_reliability | 44/44 |
| check_coding_failover | 50/50 |
| check_coding_failover_batch | 25/25 |
| check_coding_reliability | 42/42 |
| check_patch_editing | 61/61 |
| check_command_execution | 62/62 |
| check_autonomous_coding | 100/100 |
| check_request_budget_efficiency | 18/18 |

证据索引：offline-validation.json列出命令、完整分母、日志哈希、源码哈希和保护检查；synthetic-comparison.json为可复现合成对照；historical-reclassification.json保留13条历史哈希及分类；root-cause-analysis.md、failure-classification.md、security-audit.md、next-phase-readiness.md分别解释根因、规则、安全与后续边界。

## 实现范围

- Patch Schema明确完整文件64位十六进制哈希来源、先Preview和复用changes；错误反馈最多4条固定字段/类别，无原始输入值。已确认Preview的纯输入错误可修正，Write非安全错误继续停机；无法确认意图的坏JSON继续停机，没有自动重放或放宽哈希、权限、Journal。
- Controller明确受支持的unittest/pytest入口，并对成功的非认可runner给出revision-test-v1反馈。公开Benchmark提示直接来自冻结的public_test。命令仍由模型请求、逐次审批、通过原Seatbelt和Controller；python -c/打印OK不构成证据。
- Revision、开始/结束文件哈希、真实测试通过和合法模型结束仍是verified的必要条件。新通用提示提醒类型、False/0/None/空字符串、解析规则和跨模块调用链；没有Case专用解法或测试改动。
- coding-failure-v2新增来源/版本，修复edited_unverified+Hidden Pass得到null的问题；不改变Strict或Judge。13个历史结果只生成独立派生报告。

## 合成对照（synthetic）

两组使用相同4个独立公开合成任务、同一提示敏感脚本策略和相同预算：每例逻辑请求10、工具48、Write3、命令6；还保持原无进展/总时长约束。Baseline还原871510f的Schema、提示、命令观察与解析反馈；Candidate使用本次实现；原AgentLoop、原生Patch、真实Seatbelt下的unittest、工具ID均参与；此合成Fixture未启用Git Workflow，Journal/Index由原完整回归单独验证。审批提供者是离线模拟，不是真实Codex yes。

| 指标 | Baseline | Candidate |
| --- | --- | --- |
| Patch invalid_arguments | 2 | 0 |
| stale Preview（受控相同过期输入） | 1 | 1 |
| 非认可测试runner | 1 | 0 |
| 已Patch但未验证 / 已Patch任务 | 1/3 | 0/4 |
| Controller verified | 2/4 | 4/4 |
| 合成公开契约Strict Success | 2/4 | 4/4 |
| 模型逻辑请求（脚本） | 23 | 22 |
| 工具调用 | 19 | 18 |

Baseline坏哈希任务因重复动作触发原max_no_progress停止，未发生Write；runner任务完成Patch但缺有效测试。Candidate各任务仅一次正式Write；过期Preview在两组都拒绝且由脚本显式重新读取，没有自动重放。合成Strict仅指本合成公开契约真实测试、当前Revision及合法模型结束，不是历史私有Judge分数。

这证明特定脚本能够接收Schema/runner提示，原验证门仍有效；不证明真实DeepSeek/GLM能力或总体成功率提升。没有真实模型Token或费用收益证据。

## 验收问题

1. 参数错误更早发现：原Schema在validation、文件访问/发布前拒绝；本次改进是明确参数生成提示和脱敏字段诊断，没有声称历史具体错误已还原。
2. Write失败停止门：保留。非安全参数错误blocked，stale不自动重放，未新增执行器。
3. 正确测试入口：公开RuntimeCase.public_test提供明确argv；原受信runner策略提供一般建议；仍需模型发起和原审批。
4. python -c误验证：本专项的伪造Ran/OK测试被拒绝；原runner语法与非零计数验证没有放宽。
5. edited_unverified归因：现为missing_current_revision_test_evidence，source=controller；历史仅Case09发生类别变化。
6. 安全/预算：原门保持；完整取消、中断、审批、Journal、Seatbelt、工具ID、fallback物理预算、single/failover回归保留。
7. 合成证据：见表，仅脚本策略的具体行为差异与预算约束。
8. 无真实证据：真实模型遵守提示、参数错误率、任务/隐藏成功率、Token/费用、自然回退、长期取消稳定性均未验证。
9. 下一阶段：可准备新样本成对A/B；需新授权、冻结模型精确版本/两组源码/任务/评分及匹配物理预算。详见next-phase-readiness.md。

## 可复现

macOS/zsh、Python3.12+、uv。在目标worktree运行：

```bash
uv sync --frozen
uv run python -m scripts.check_tool_verification_reliability
uv run python -m scripts.check_coding_failover
uv run python -m scripts.check_coding_failover_batch
uv run python -m scripts.check_coding_reliability
uv run python -m scripts.check_patch_editing
uv run python -m scripts.check_command_execution
uv run python -m scripts.check_phase
uv run python -m compileall -q mybot scripts
git diff --check
```

导出合成/历史派生结果到新路径（不覆盖原历史）：

```bash
uv run python -m scripts.check_tool_verification_reliability --comparison /tmp/tool-verification-synthetic.json
uv run python -m scripts.check_tool_verification_reliability --reanalyze /tmp/tool-verification-history.json
```

源码运行期间保持稳定；原freeze机制会拒绝中途源码变化。所有入口默认离线；本轮无Live重测。
