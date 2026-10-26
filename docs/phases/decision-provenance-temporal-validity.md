# Decision Provenance & Temporal Validity v1 学习专题

未编号工程专题；不创建或移动历史Phase Tag/ZIP。接续Source-Aware真实UAT发现的推断强化、时序混淆和内部标签复述。完整状态和限制见[验收报告](../reports/decision-provenance-temporal-validity/acceptance-report.md)。

## 学习目标与概念

来源归属不是语义蕴含：用户禁止自动删除不等于永久保留。精确用户原文和宿主Pin确认事件分别回答“谁说过”与“用户是否显式固定过”。助手建议、推断与普通原文中的可选/未决含义不因关键词自动变成已确认决定。当前有效与过去曾有效分开，撤销不追溯改变过去。

## 架构、核心文件与调用关系

DecisionProvenance.statement校验SQLite消息角色/Session/Unicode跨度/完整性。DecisionProvenance.view→DecisionTimeline.view在只读快照中核对事件哈希并计算提交边界区间。SessionEventStore.append_many在原事务内写event_commits；事件Schema仍v1，DB v2增加提交区间，v1迁移不发明旧边界。SessionHistory.decisions供Web状态和CLI `/decisions [boundary]`读取；普通模型回答不在证据路径中。

context_projection继续遮蔽具体失效来源，保留独立事实与协议组。新的自然语言政策解释更强改写、建议和历史有效性，仍经ContextManager和TokenCounter原预算。Web固定事项详情显示原文、生效/失效顺序与确认事件；普通模型回答有独立展示和非确认提示。不增加System权限或模型工具。

## macOS + uv 安装、运行、测试

```bash
uv sync --frozen
uv run python mybot/main.py
# CLI: /decisions 或 /decisions <已提交序号>
uv run python -m scripts.check_decision_provenance
uv run python -m scripts.check_decision_timeline
uv run python -m scripts.check_decision_context
uv run python -m scripts.check_phase
uv run python -m scripts.check_persistent_session_uat
uv run python -m scripts.check_source_aware_uat
uv run python -m compileall -q mybot scripts
node --check mybot/web/static/app.js
uv run --no-project --python 3.12 --with playwright python scripts/decision_browser_acceptance.py
```

Chrome验收使用独立0700临时profile、同Origin双profile隔离探针、8898合成服务。不会访问旧私有Live库或生产凭证；Playwright不进入生产依赖。机器Chrome路径见可选驱动，其他机器应修改自己运行副本中的显式可执行路径，不变更生产安全策略。

## 实际案例与结果

56个新增断言覆盖来源20、时间线20、上下文16。合成“永久保留已确定”普通回答保留错误原文，可信集合仍是两个精确Pin。旧名→新名→撤销三个提交边界分别旧/新/空，同事务内部拒绝查询。跨默认六轮与重启后时间线保持，不恢复审批/Receipt。真实Chrome完成确认/替换/撤销/重启，12次本地SyntheticClient调用，真实Provider0。

## 常见问题与上阶段变化

旧库没有提交区间时早期历史查询会拒绝，不是猜测Pin不存在。null端点不能按当前时间倒填。预算不足仍可拒绝参考或遗漏历史；source_verified不是语义正确性。与上一专题相比，本阶段补上决定确认链与已提交历史边界，保留原Source Preservation、Tool Authority和上下文预算。自由文本语义误判与抄标签仍需未来另行授权Live验证。
