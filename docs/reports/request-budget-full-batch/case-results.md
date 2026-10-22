# 全部13个计划Attempt

本表保留全部计划分母，受控组不混入自然组。null表示不可观测。

| 槽位 | 难度/组 | Attempt ID | Agent | Hidden | Workflow | Strict | 失败 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 01-config-default-001 | easy/natural | 755ad819e3014c649a2aa2768277106f | verified | hidden_fail | True | False | public_tests_only |
| 02-cache-ttl-001 | easy/natural | 6bfcd6e49b07486bb797cd723a7d414e | verified | hidden_pass | True | True | null（原failure字段） |
| 03-pagination-001 | easy/natural | 83c28eacc1a1494a934280acc262436b | verified | hidden_pass | True | True | null（原failure字段） |
| 04-serialization-001 | easy/natural | 1e5eace840ea47ba9fbdcce9ab812aae | verified | hidden_pass | True | True | null（原failure字段） |
| 05-csv-export-001 | medium/natural | e40377aa1790483580ec638dfc707f79 | verified | hidden_pass | True | True | null（原failure字段） |
| 06-timezone-day-001 | medium/natural | b8cf62dd96c74c3a93816660b016e29c | blocked | hidden_fail | False | False | patch_failed_without_safe_recovery |
| 07-file-recovery-001 | medium/natural | d26b7b2b3ae74823aebbc1e6ab737754 | verified | hidden_pass | True | True | null（原failure字段） |
| 08-cli-precedence-001 | medium/natural | 2e2a9498cb854ad4b52eb5cc69f1e937 | verified | hidden_pass | True | True | null（原failure字段） |
| 09-validation-chain-001 | hard/natural | 274fc515a05342c69ae04a056c0c5bdf | edited_unverified | hidden_pass | False | False | null（原failure字段） |
| 10-cache-sync-001 | hard/natural | b0f9da8b08784eaead079eeab5f8db89 | verified | hidden_pass | True | True | null（原failure字段） |
| 11-parse-convert-001 | hard/natural | 7131275c2a224676b1bd1dbae00089ad | verified | hidden_fail | True | False | public_tests_only |
| 12-error-retry-001 | hard/natural | 300fb004b209496e8a0f65f9e15ed399 | verified | hidden_pass | True | True | null（原failure字段） |
| 13-forced-failover-coding | easy/controlled | f128c557d3634c6cb5f64b5b9261abbc | budget_exhausted | hidden_pass | False | False | model_request_budget |

| 槽位 | 逻辑/物理/HTTP | coco/coco2 | 回退 | Patch/真实测试 | 当前/验证Revision | 审批 | 输入/输出Token（可观察真实请求） | 秒 | 清理 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 01-config-default-001 | 11/11/11 | 11/0 | NOT_TRIGGERED | 1/1 | 1/1 | 1 | 44719/1500 | 62.654 | True |
| 02-cache-ttl-001 | 8/8/8 | 8/0 | NOT_TRIGGERED | 1/1 | 1/1 | 1 | 31231/980 | 43.419 | True |
| 03-pagination-001 | 9/9/9 | 9/0 | NOT_TRIGGERED | 1/1 | 1/1 | 2 | 36025/1287 | 64.756 | True |
| 04-serialization-001 | 9/9/9 | 9/0 | NOT_TRIGGERED | 1/1 | 1/1 | 1 | 35749/1168 | 43.918 | True |
| 05-csv-export-001 | 9/9/9 | 9/0 | NOT_TRIGGERED | 1/1 | 1/1 | 2 | 34509/1126 | 85.365 | True |
| 06-timezone-day-001 | 5/5/5 | 5/0 | NOT_TRIGGERED | 0/0 | 0/None | 0 | 16922/671 | 23.267 | True |
| 07-file-recovery-001 | 10/10/10 | 10/0 | NOT_TRIGGERED | 1/1 | 1/1 | 1 | 44979/2188 | 64.120 | True |
| 08-cli-precedence-001 | 8/8/8 | 8/0 | NOT_TRIGGERED | 1/1 | 1/1 | 1 | 37615/1665 | 59.990 | True |
| 09-validation-chain-001 | 15/15/15 | 15/0 | NOT_TRIGGERED | 1/0 | 1/None | 6 | 92248/2627 | 298.638 | True |
| 10-cache-sync-001 | 14/14/14 | 14/0 | NOT_TRIGGERED | 2/1 | 2/2 | 1 | 63479/1584 | 143.536 | True |
| 11-parse-convert-001 | 10/10/10 | 10/0 | NOT_TRIGGERED | 1/1 | 1/1 | 1 | 47068/2278 | 117.774 | True |
| 12-error-retry-001 | 7/7/7 | 7/0 | NOT_TRIGGERED | 1/1 | 1/1 | 1 | 27908/1117 | 71.078 | True |
| 13-forced-failover-coding | 11/12/11 | 1/11 | INJECTED | 1/1 | 1/1 | 2 | 43101/1507 | 149.113 | True |

逐例公开测试、Patch错误阶段、Token完整性、Journal哈希、完整Controller与生命周期字段均在batch-summary.json；v4原始脱敏报告副本见evidence。HTTP为发送前观察，不是供应商计费确认；注入物理1、HTTP0，其Usage为null且不冒充真实模型Token。

第9例原failure=null，但controller.stop_reason明确为missing_current_revision_test_evidence；不能把null当作成功。新报告analysis_category据此分类，原始raw不修改。受控组repeated_actions=1，表示模型的一次重复动作计数；正式Patch仍只有1次，不冒充所有模型工具动作均无重复。

| 槽位 | 公开Judge | 工具数 | Preview成功/调用 | Agent状态/停止原因 | lifecycle/uncertain |
| --- | --- | --- | --- | --- | --- |
| 01-config-default-001 | pass (2) | 14 | 1/2 | verified / 正常结束 | completed / False |
| 02-cache-ttl-001 | pass (2) | 11 | 1/1 | verified / 正常结束 | completed / False |
| 03-pagination-001 | pass (2) | 10 | 1/2 | verified / 正常结束 | completed / False |
| 04-serialization-001 | pass (2) | 10 | 1/2 | verified / 正常结束 | completed / False |
| 05-csv-export-001 | pass (2) | 14 | 0/1 | verified / 正常结束 | completed / False |
| 06-timezone-day-001 | pass (2) | 9 | 0/0 | blocked / patch_failed_without_safe_recovery | completed / False |
| 07-file-recovery-001 | pass (2) | 14 | 1/2 | verified / 正常结束 | completed / False |
| 08-cli-precedence-001 | pass (2) | 13 | 1/1 | verified / 正常结束 | completed / False |
| 09-validation-chain-001 | pass (2) | 21 | 1/2 | edited_unverified / missing_current_revision_test_evidence | completed / False |
| 10-cache-sync-001 | pass (2) | 17 | 2/3 | verified / 正常结束 | completed / False |
| 11-parse-convert-001 | pass (2) | 17 | 1/2 | verified / 正常结束 | completed / False |
| 12-error-retry-001 | pass (2) | 14 | 0/0 | verified / 正常结束 | completed / False |
| 13-forced-failover-coding | pass (2) | 11 | 1/4 | budget_exhausted / max_model_requests | completed / False |
