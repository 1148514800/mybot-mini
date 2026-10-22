# AI_HANDOFF

## 当前目标与状态

Tool Reliability & Verification Closure：独立分支codex/tool-verification-reliability，基线871510f8a682990da63448ef27ec282c376a8711。Implementation 04b6968fdab288d8562447e25c84a6d5cec3df41；最终离线回归通过；不是Phase26，不合并main，不移动Tag/ZIP。本轮授权Push本分支；实现与验收文档分两次提交，交付入口docs/reports/tool-verification-reliability/acceptance-report.md。

## 实现与架构

- 原Patch Schema补充64位完整文件哈希来源和Preview→Write复用changes的提示。原校验失败后最多4条白名单字段/类别反馈，不输出输入值、Patch正文或敏感路径。Preview纯输入恢复沿用原规则；未知意图坏JSON仍停止，Write非安全错误仍blocked；不自动重放。
- Controller补充受信unittest/pytest入口建议，成功的非认可runner返回revision-test-v1反馈。Benchmark提示仅来自冻结RuntimeCase.public_test。原Revision/哈希/真实测试/合法模型结束门、审批、Seatbelt、Journal和预算不改。
- 通用类型、解析和跨模块边界提示；不含Case解法，Benchmark公开/隐藏资产未改。coding-failure-v2返回来源/版本，修复edited_unverified+Hidden Pass的null归因，不改Strict/Judge/Controller。
- 改动：patch、coding_controller、loop解析反馈、coding_benchmark、coding_metrics、check_phase；新增check_tool_verification_reliability和完整报告。没有新执行器或依赖。

## 验证与证据

干净基线1114/1114（31套件）；新增44/44；最终全量1158/1158（32套件），无跳过。独立failover50、Batch25、可靠性42、Patch61、命令62、自主编码100、效率18全部通过；编译/diff检查通过。原取消、中断、预算、审批、工具ID、Journal/Index和Seatbelt回归保留。

同预算4例synthetic：verified/公开合成Strict 2→4；invalid_arguments 2→0，stale Preview 1→1，非认可runner1→0；已Patch未验证1/3→0/4；逻辑请求23→22、工具19→18。策略脚本对提示敏感，仅证明反馈链路，不是实际模型能力提升；合成Fixture未启用Git Workflow，Journal由原回归验证。

历史13条只读重新分类仅Case09由null变为missing_current_revision_test_evidence；自然Strict8/12、受控0/1不变。原13个运行raw与冻结副本13/13哈希匹配；历史报告/Canary/Phase25/Benchmark、main、全部Tag、53个旧ZIP保持原值。真实模型HTTP0、付费Judge0、Codex真实yes审核0；没有Live补跑。

## 已知边界与下一步

精确历史非法Patch字段unknown；坏JSON意图unknown仍保守停止。真实模型提示遵循、泛化、Token/费用收益、长期取消可靠性未验证。工程准备READY；真实新样本A/B仍需新授权，固定双方模型版本、源码/评分、任务、逻辑和物理预算。不要复用旧13例声称未见，不改历史分数或归档，不擅自进入Phase26。

开发中压缩提示遗漏cwd/timeout原明确措辞，已恢复并通过原断言；中途改源码触发冻结拒绝后，稳定源码重跑通过。不要删断言或放宽冻结来处理这两类情况。当前报告只保留状态，历史过程查Git。
