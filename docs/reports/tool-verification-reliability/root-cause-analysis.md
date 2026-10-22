# 只读根因诊断

基线：origin/codex/request-budget-full-batch，871510f8a682990da63448ef27ec282c376a8711。Fetch 已核对。资料为原 failure-analysis/case-results/next-phase-readiness、脱敏 raw 的 Controller/metrics/trace 元数据、公开任务说明和公开测试，以及生产 Harness。未读取历史隐藏断言、Gold 或 Reference 解法。执行原离线回归时，原 Judge 自行使用冻结资产；这些资产没有作为提示或调参依据。

| 案例 | 可直接确认 | 不能推断 |
| --- | --- | --- |
| 06 timezone | 唯一正式 Write 在 validation 失败，invalid_arguments / preflight_failed / safe_to_retry=false；Revision 0，未提交，Controller blocked | 原始 Patch 参数未保存；具体非法字段 unknown，不能称为发布/磁盘失败 |
| 09 validation-chain | Revision 1；test_runs=3/test_passes=0，last_verified_revision=null；edited_unverified，missing_current_revision_test_evidence。末次 python -c 成功不构成受认可 runner 证据 | Hidden Pass 不意味着 Agent 合法结束；不推断失败测试的具体业务断言 |
| 01 config-default | Agent verified，公开测试2项，Hidden Fail；公开任务区分显式False、缺省和非bool，公开测试只有True和缺省两类 | 不知道隐藏失败的精确输入，不将它归因为某一未观察断言 |
| 11 parse-convert | Agent verified，公开测试2项，Hidden Fail；公开任务含分隔、空白、空键、转换和重复规则，公开测试仅普通文本及空列表 | 不知道隐藏失败的精确输入；stale Preview 与最终隐藏失败没有可证因果关系 |
| 13 controlled GLM | 1次stale Preview、2次validation invalid_arguments Preview；随后Patch与真实unittest有效。物理12次耗尽（1次本地注入、11次HTTP），未合法结束 | 不假设额外一次请求必成功；不将此受控案例当作自然恢复率或TASK PASS |

本次措施：为哈希字段与 Preview→Write 结构增加明确 Schema 提示；纯 Schema 错误仅返回最多4条白名单字段位置与校验类别；成功但不被认可的测试命令得到结构化提示。公开 Benchmark 入口直接来自 RuntimeCase.public_test（原加载器仅接受冻结的公开 unittest 命令），不来自 Judge。Controller 增加通用类型/解析/调用链边界检查原则，不硬编码案例答案，不修改任何 Benchmark 测试。

完整 JSON 无法解析时，无法可信确认 Preview 意图，保留 safe_to_retry=false 和停机；可确认的 Preview Schema 错误沿用原 safe_to_retry 策略。没有扩大 Write 恢复许可，没有添加自动重试。

历史重新分类见 historical-reclassification.json：13条，每条保留原 raw SHA256、原failure及新来源/版本。只读提取元数据，原 Attempt、Campaign、Canary、Phase25 文件不回写。
