# Phase25-R：取消生命周期与评测可靠性修复

这是Phase25归档之后的离线修复，未重建或移动原phase-25归档。

完整学习说明、历史证据链、状态机、审批输入、Journal采样、断点恢复、验证和限制见[修复验收报告](../reports/phase-25-r/acceptance-report.md)；逐次只读审计见[历史审计](../reports/phase-25-r/historical-audit.json)。

核心调用关系：Campaign.run_next绑定Attempt → evaluate/run_task → Attempt.run取消屏障 → 原BenchmarkAgent/AgentLoop → CodingClient和工具边界校验 → Journal哈希采样 → 原Judge → terminal/raw/finished证据。新Campaign采用真实TTY的每命令挑战审批，取消后失效。未知清理保留Workspace并停止，不自动重试。

macOS/uv离线复习：

```bash
uv run python -m scripts.audit_phase25r
uv run python -m scripts.check_coding_reliability
uv run python -m compileall -q mybot scripts
uv run python -m scripts.check_phase
git diff --check
```

本轮仅离线，不执行真实API、不改模型配置、不归档、不Push/Merge、不进入26。任何新的coco/deepseek-v4.1-flash Live必须另获授权，独立新建Cohort，不混合旧Astra的36次数据。
