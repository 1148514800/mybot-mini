# Patch Preview Receipt Reliability 验收

**OFFLINE PASS**。基线 `cc8f00ad661292da0db433324e2ae2e14143b367`；Implementation `cd8f856e885d677daa89a38e71539cb638f513e0`。独立分支 `codex/patch-preview-receipt`。本报告所属提交为 Acceptance Commit，可通过 Git 查询；最终远程 HEAD 另在交付时核对。没有合并 main、创建/移动 Tag 或导出 ZIP，不是新的 Phase 归档。

Receipt 协议实际可用：显式 Preview 生成单次、最长 300 秒的随机能力，显式 Commit 只需 dry_run=false 和 receipt，不再生成复杂 changes。原修改快照和全部文件版本绑定；stale、元数据/inode/目录替换、新增目标出现、跨 turn/Workspace、重放都安全拒绝。全部 Write 停止门、原发布/回滚/Journal 与当前 Revision 测试要求保留。默认 Legacy 不变；可显式配置 coding.preview_receipt=true，原生 ApplyPatchTool 类型保持一致。

| 离线命令 | unittest 数 | suites | 结果 |
|---|---:|---:|---|
| `uv run python -m scripts.check_patch_preview_receipt` | 53 | 1 | PASS |
| `uv run python -m scripts.check_patch_editing` | 61 | 1 | PASS |
| `uv run python -m scripts.check_tool_verification_reliability` | 44 | 1 | PASS |
| `uv run python -m scripts.check_tool_verification_live_ab` | 29 | 1 | PASS |
| `uv run python -m scripts.check_coding_failover` | 50 | 1 | PASS |
| `uv run python -m scripts.check_coding_failover_batch` | 25 | 1 | PASS |
| `uv run python -m scripts.check_coding_reliability` | 42 | 1 | PASS |
| `uv run python -m scripts.check_phase` | 1240 | 34 | PASS |

原有 **1187/1187** 原样保留；新增 **53/53**；全量 **1240/1240、34 套件、0 skip**。单独命令与全量重复运行的是同一断言，不能累加成唯一用例总数。compileall 与 git diff --check 也通过。single/failover/v4 兼容性由原套件覆盖。完整计数、日志 SHA、运行耗时和源码 manifest 见 [offline-validation.json](offline-validation.json)。

| 合成指标（每组 12 条件） | Legacy | Receipt |
|---|---:|---:|
| 参数错误 | 2 | 0 |
| 成功提交 / 全条件 | 4/12 | 4/12 |
| 成功提交 / 正式尝试 | 4/8 | 4/8 |
| Controller verified | 4 | 4 |
| synthetic_contract_success（公开合同代理） | 4 | 4 |
| 正式 Strict Success | 0（离线不适用） | 0（离线不适用） |
| 实际工具执行 | 25 | 24 |
| 合成逻辑/物理请求 | 33/33 | 31/31 |
| 安全拒绝 / 全工具失败 | 2/6 | 4/5 |
| execution_uncertain | 1 | 1 |

二次 changes 损坏条件 Receipt 胜；权限变化条件 Receipt 额外拒绝，Legacy 继续保留提交时 mode。总体提交/验证持平，既有改善也有额外停止。原 Strict 规则要求 Live 和私有 Judge，本轮未运行，未用公开合同代理改写 Strict。全部条件、负例及分母保存在两份内容相同的 [synthetic-comparison.json](synthetic-comparison.json) 与 [synthetic-receipt-comparison.json](synthetic-receipt-comparison.json)。合成只能证明协议行为，不能证明真实 DeepSeek/GLM 成功率或费用提升。

真实模型 API/HTTP **0**；实际操作员 yes/yes nonce **0**。本轮仅用临时 Workspace、公开合成合同和模拟客户端/审批；旧轮剩余 68 次授权未使用。1034 个受保护历史文件、main、26 Tag、53 ZIP/AppleDouble、原 13 个 Attempt 与最近 8 个 A/B Attempt 校验不变；旧原始参数未恢复，旧评分/私有测试未修改。

安全审计见 [security-audit.md](security-audit.md)，协议与继承限制见 [architecture.md](architecture.md)，完整解释见 [failure-analysis.md](failure-analysis.md)。下一阶段仅准备新的 8 对配对方案、相同模型与预算、USD 5.00 建议硬上限，须可靠单价和新 Live 授权后另行冻结执行，见 [next-phase-readiness.md](next-phase-readiness.md)。最大的剩余风险是供应商 Schema/模型行为、上下文裁剪/TTL，以及更严格一致性导致额外拒绝。
