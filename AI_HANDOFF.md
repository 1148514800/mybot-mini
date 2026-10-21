# AI_HANDOFF

## 当前状态

Phase25-R在codex/phase-25、`/Users/godblack/.codex/worktrees/phase-25/mybot-mini`已完成离线后续可靠性修复，基线8acf9ab。功能、42项专项和固定源码最终991项/26套件回归全部通过；原949项/25套件及测试文件保留。只做本地新提交，不归档/Push/Merge，不进入26。

## 历史事实与证据

原标准Harness b008f35563c266d89ebbdd67a3c31607f9c47819，coco2/gpt-6-astra，36次全保留：严格15/36，hidden_pass31/36、Judge repair18/36，取消13次、Journal累计26文件记录。原API元数据没有输入线程栈，审批等待归因结合操作事件及计数，不伪称逐次堆栈证明。外部6请求/5响应、第6次超时、0 Patch/Agent测试，仍未通过。历史异常不重算归属，不排除分母。

原170份证据SHA及184项报告/ZIP/config/用户文件保护资产已核对；phase-25仍指向8acf9ab，原ZIP SHA256为2686325f14d47d133e642cb4aeef7db813f3c71771fe224bab43039754beb57c。main、历史Tag/ZIP和用户配置不变。新证据只在docs/reports/phase-25-r，不重写旧报告。

## 实现与安全边界

保留29fedef已有停止门与单槽解释器隔离，保留e7a1f39的resolve路径修复。新增评测层Attempt身份/不可逆撤销/5秒有界清理屏障；CodingClient与BenchmarkAgent请求/工具前后检查，取消后不启动后续Case/Repeat/Slot。清理未确认保留临时Workspace并严格execution_uncertain，不自动重试。SDK关闭和重复进程中断不能覆盖取消。

Phase25 Campaign/外部入口使用真实TTY的可取消FD读入和每命令随机挑战`yes <nonce>`，无后台input线程、无授权缓存；原通用cli_command_approval不改。直接旧评测API兼容yes，但新Cohort须走绑定身份的Campaign入口。

工具边界在原Loop关闭Journal前保存公开路径和original/final哈希，校验初始与最终字节后才接受归属；丢失/冲突/pending保持异常。保存Tool Call ID哈希终态账本，不伪造已执行或成功结果。manifest v3冻结实际配置模型和源码/预算/Schema；started/terminal/raw/finished/blocked交叉验证Campaign/Run/Attempt/配置与SHA，已完成不重放，blocked优先于表面verified。

未修改AgentLoop、Controller、Patch、run_command验证、command_process、Seatbelt、Fixture/Gold/Reference/隐藏测试、Judge、依赖或模型凭证。所有模型均为合成客户端，无真实模型API、付费Live或外部项目模型复测。42项专项包含真实PTY、合成取消/迟到回调、原生Patch+Seatbelt真实测试+Judge、Journal异常和恢复/统计反例。最终回归、编译、diff检查及184项保护资产再次验证通过；回执docs/reports/phase-25-r/validation-summary.json。

## 学习与下一步

完整根因、13次/26文件证据链、状态机、验证与限制见docs/reports/phase-25-r/acceptance-report.md；学习入口docs/phases/phase-25-r.md；只读审计`uv run python -m scripts.audit_phase25r`。

已完成全量、编译、diff及保护资产核对；本轮仅创建一个明确标记Phase25后续修复的本地提交，SHA见Git记录。不得移动phase-25、重新导出ZIP或修改旧36报告。离线通过不等于Live稳定性验收；新coco/deepseek-v4.1-flash重复Cohort须另获费用授权、新目录/提交/冻结配置，不与旧Astra混算，不自动执行。
