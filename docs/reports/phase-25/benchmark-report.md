# Phase25 固定 Cohort：有操作中断混杂的实测结果

36/36槽位均产生原始报告，严格成功15/36；此分母保留所有失败。Round1 9/12、Round2 6/12、Round3 0/12。不能据此声称模型三轮稳定性下降。
执行事故：审批值守中断后，原编排仅拦截execution_uncertain，却未拦截cancelled/task_timeout；13个槽位在审批等待中取消。未向过期提示发送yes。原Loop取消后清除capsule，评测归属集合缺失，产生13次Journal不匹配（共26文件），即使Judge隐藏测试通过也不计完整成功。
事后V2在编排层添加中断调查门和继承真实TTY的单槽进程隔离，离线验证通过；不修改原36份报告，不重跑标准案例。V2不是本Cohort的执行版本，也没有新的标准Live证据。
# Phase25 标准 Benchmark

计划 36；完成 36；未执行 0；不确定 0。
严格成功 15；已完成运行成功率 0.4166666666666667；至少一次成功覆盖 11。
未完成轮次不能称为全量 pass@1；历史覆盖不是单次成功率。未知费用为 null，不代表免费。

| Run ID | 状态 | Agent | Judge | 严格成功 | 失败分类 |
|---|---|---|---|---|---|
| r1-pagination-001 | completed | blocked | hidden_fail | False | ['patch_commit_failed', 'invalid_tool_arguments', 'real_test_not_executed', 'hidden_tests_failed'] |
| r1-serialization-001 | completed | verified | hidden_pass | True | ['success'] |
| r1-file-recovery-001 | completed | blocked | hidden_fail | False | ['model_request_timeout', 'real_test_not_executed', 'hidden_tests_failed'] |
| r1-config-default-001 | completed | verified | hidden_pass | True | ['success'] |
| r1-cache-ttl-001 | completed | verified | hidden_pass | True | ['success'] |
| r1-csv-export-001 | completed | verified | hidden_pass | True | ['success'] |
| r1-timezone-day-001 | completed | budget_exhausted | hidden_pass | False | ['request_budget_exhausted'] |
| r1-cli-precedence-001 | completed | verified | hidden_pass | True | ['success'] |
| r1-validation-chain-001 | completed | verified | hidden_pass | True | ['success'] |
| r1-cache-sync-001 | completed | verified | hidden_pass | True | ['success'] |
| r1-parse-convert-001 | completed | verified | hidden_pass | True | ['success'] |
| r1-error-retry-001 | completed | verified | hidden_pass | True | ['success'] |
| r2-pagination-001 | completed | verified | hidden_pass | True | ['success'] |
| r2-serialization-001 | completed | verified | hidden_pass | True | ['success'] |
| r2-file-recovery-001 | completed | verified | hidden_pass | True | ['success'] |
| r2-config-default-001 | completed | verified | hidden_pass | True | ['success'] |
| r2-cache-ttl-001 | completed | verified | hidden_pass | True | ['success'] |
| r2-csv-export-001 | completed | verified | hidden_pass | True | ['success'] |
| r2-timezone-day-001 | completed | budget_exhausted | hidden_pass | False | ['request_budget_exhausted'] |
| r2-cli-precedence-001 | completed | budget_exhausted | hidden_pass | False | ['request_budget_exhausted'] |
| r2-validation-chain-001 | completed | cancelled | hidden_pass | False | ['task_timeout', 'agent_interrupted', 'real_test_not_executed', 'revision_or_journal_mismatch', 'supervisor_audit_required'] |
| r2-cache-sync-001 | completed | cancelled | hidden_pass | False | ['task_timeout', 'agent_interrupted', 'real_test_not_executed', 'revision_or_journal_mismatch', 'supervisor_audit_required'] |
| r2-parse-convert-001 | completed | cancelled | hidden_pass | False | ['task_timeout', 'agent_interrupted', 'real_test_not_executed', 'revision_or_journal_mismatch', 'supervisor_audit_required'] |
| r2-error-retry-001 | completed | cancelled | hidden_pass | False | ['task_timeout', 'agent_interrupted', 'real_test_not_executed', 'revision_or_journal_mismatch', 'supervisor_audit_required'] |
| r3-pagination-001 | completed | cancelled | hidden_pass | False | ['task_timeout', 'agent_interrupted', 'real_test_not_executed', 'revision_or_journal_mismatch', 'supervisor_audit_required'] |
| r3-serialization-001 | completed | budget_exhausted | hidden_fail | False | ['request_budget_exhausted', 'patch_preview_failed', 'invalid_tool_arguments', 'real_test_not_executed', 'hidden_tests_failed'] |
| r3-file-recovery-001 | completed | cancelled | hidden_pass | False | ['task_timeout', 'agent_interrupted', 'real_test_not_executed', 'revision_or_journal_mismatch', 'supervisor_audit_required'] |
| r3-config-default-001 | completed | cancelled | hidden_pass | False | ['task_timeout', 'agent_interrupted', 'real_test_not_executed', 'revision_or_journal_mismatch', 'supervisor_audit_required'] |
| r3-cache-ttl-001 | completed | blocked | hidden_fail | False | ['patch_commit_failed', 'invalid_tool_arguments', 'real_test_not_executed', 'hidden_tests_failed'] |
| r3-csv-export-001 | completed | cancelled | hidden_pass | False | ['task_timeout', 'agent_interrupted', 'real_test_not_executed', 'revision_or_journal_mismatch', 'supervisor_audit_required'] |
| r3-timezone-day-001 | completed | cancelled | hidden_pass | False | ['task_timeout', 'agent_interrupted', 'real_test_not_executed', 'revision_or_journal_mismatch', 'supervisor_audit_required'] |
| r3-cli-precedence-001 | completed | cancelled | hidden_pass | False | ['task_timeout', 'agent_interrupted', 'real_test_not_executed', 'revision_or_journal_mismatch', 'supervisor_audit_required'] |
| r3-validation-chain-001 | completed | budget_exhausted | hidden_fail | False | ['no_progress_budget_exhausted', 'patch_commit_failed', 'real_test_not_executed', 'hidden_tests_failed'] |
| r3-cache-sync-001 | completed | cancelled | hidden_pass | False | ['task_timeout', 'agent_interrupted', 'real_test_not_executed', 'revision_or_journal_mismatch', 'supervisor_audit_required'] |
| r3-parse-convert-001 | completed | cancelled | hidden_pass | False | ['task_timeout', 'agent_interrupted', 'real_test_not_executed', 'revision_or_journal_mismatch', 'supervisor_audit_required'] |
| r3-error-retry-001 | completed | cancelled | hidden_pass | False | ['task_timeout', 'agent_interrupted', 'real_test_not_executed', 'revision_or_journal_mismatch', 'supervisor_audit_required'] |


## 12例 × 3轮

成功=Agent工作流/Judge/真实测试及安全均通过。失败不会从分母删除；未执行不是已完成失败。

| 案例 | Round1 | Round2 | Round3 | 完整成功次数 |
|---|---|---|---|---|
| pagination-001 | blocked/hidden_fail: patch_commit_failed,invalid_tool_arguments,real_test_not_executed,hidden_tests_failed | 成功 | cancelled/hidden_pass: task_timeout,agent_interrupted,real_test_not_executed,revision_or_journal_mismatch,supervisor_audit_required | 1/3 |
| serialization-001 | 成功 | 成功 | budget_exhausted/hidden_fail: request_budget_exhausted,patch_preview_failed,invalid_tool_arguments,real_test_not_executed,hidden_tests_failed | 2/3 |
| file-recovery-001 | blocked/hidden_fail: model_request_timeout,real_test_not_executed,hidden_tests_failed | 成功 | cancelled/hidden_pass: task_timeout,agent_interrupted,real_test_not_executed,revision_or_journal_mismatch,supervisor_audit_required | 1/3 |
| config-default-001 | 成功 | 成功 | cancelled/hidden_pass: task_timeout,agent_interrupted,real_test_not_executed,revision_or_journal_mismatch,supervisor_audit_required | 2/3 |
| cache-ttl-001 | 成功 | 成功 | blocked/hidden_fail: patch_commit_failed,invalid_tool_arguments,real_test_not_executed,hidden_tests_failed | 2/3 |
| csv-export-001 | 成功 | 成功 | cancelled/hidden_pass: task_timeout,agent_interrupted,real_test_not_executed,revision_or_journal_mismatch,supervisor_audit_required | 2/3 |
| timezone-day-001 | budget_exhausted/hidden_pass: request_budget_exhausted | budget_exhausted/hidden_pass: request_budget_exhausted | cancelled/hidden_pass: task_timeout,agent_interrupted,real_test_not_executed,revision_or_journal_mismatch,supervisor_audit_required | 0/3 |
| cli-precedence-001 | 成功 | budget_exhausted/hidden_pass: request_budget_exhausted | cancelled/hidden_pass: task_timeout,agent_interrupted,real_test_not_executed,revision_or_journal_mismatch,supervisor_audit_required | 1/3 |
| validation-chain-001 | 成功 | cancelled/hidden_pass: task_timeout,agent_interrupted,real_test_not_executed,revision_or_journal_mismatch,supervisor_audit_required | budget_exhausted/hidden_fail: no_progress_budget_exhausted,patch_commit_failed,real_test_not_executed,hidden_tests_failed | 1/3 |
| cache-sync-001 | 成功 | cancelled/hidden_pass: task_timeout,agent_interrupted,real_test_not_executed,revision_or_journal_mismatch,supervisor_audit_required | cancelled/hidden_pass: task_timeout,agent_interrupted,real_test_not_executed,revision_or_journal_mismatch,supervisor_audit_required | 1/3 |
| parse-convert-001 | 成功 | cancelled/hidden_pass: task_timeout,agent_interrupted,real_test_not_executed,revision_or_journal_mismatch,supervisor_audit_required | cancelled/hidden_pass: task_timeout,agent_interrupted,real_test_not_executed,revision_or_journal_mismatch,supervisor_audit_required | 1/3 |
| error-retry-001 | 成功 | cancelled/hidden_pass: task_timeout,agent_interrupted,real_test_not_executed,revision_or_journal_mismatch,supervisor_audit_required | cancelled/hidden_pass: task_timeout,agent_interrupted,real_test_not_executed,revision_or_journal_mismatch,supervisor_audit_required | 1/3 |

## 轮次与资源

```json
{
  "rounds": {
    "1": {
      "planned": 12,
      "completed": 12,
      "strict_successes": 9,
      "completed_run_success_rate": 0.75,
      "round_complete": true
    },
    "2": {
      "planned": 12,
      "completed": 12,
      "strict_successes": 6,
      "completed_run_success_rate": 0.5,
      "round_complete": true
    },
    "3": {
      "planned": 12,
      "completed": 12,
      "strict_successes": 0,
      "completed_run_success_rate": 0.0,
      "round_complete": true
    }
  },
  "difficulty": {
    "easy": {
      "completed": 12,
      "strict_successes": 7
    },
    "medium": {
      "completed": 12,
      "strict_successes": 4
    },
    "hard": {
      "completed": 12,
      "strict_successes": 4
    }
  },
  "resources": {
    "llm_requests": {
      "known": 36,
      "missing": 0,
      "total": 308,
      "mean": 8.555555555555555,
      "p50": 8.0,
      "p90": 12.0,
      "p95": 12.0
    },
    "successful_responses": {
      "known": 36,
      "missing": 0,
      "total": 307,
      "mean": 8.527777777777779,
      "p50": 8.0,
      "p90": 12.0,
      "p95": 12.0
    },
    "tool_calls": {
      "known": 36,
      "missing": 0,
      "total": 540,
      "mean": 15.0,
      "p50": 13.5,
      "p90": 22.5,
      "p95": 23.0
    },
    "input_tokens": {
      "known": 35,
      "missing": 1,
      "total": 1021493,
      "mean": 29185.514285714286,
      "p50": 25733.0,
      "p90": 43704.00000000001,
      "p95": 45896.2
    },
    "output_tokens": {
      "known": 35,
      "missing": 1,
      "total": 99643,
      "mean": 2846.942857142857,
      "p50": 2545.0,
      "p90": 4189.8,
      "p95": 4628.7
    },
    "total_tokens": {
      "known": 35,
      "missing": 1,
      "total": 1121136,
      "mean": 32032.457142857143,
      "p50": 28205.0,
      "p90": 47458.4,
      "p95": 49240.6
    },
    "duration_seconds": {
      "known": 36,
      "missing": 0,
      "total": 10947.906468,
      "mean": 304.10851299999996,
      "p50": 177.8607985,
      "p90": 600.5494564999999,
      "p95": 600.55426425
    },
    "patch_preview_calls": {
      "known": 36,
      "missing": 0,
      "total": 41,
      "mean": 1.1388888888888888,
      "p50": 1.0,
      "p90": 1.0,
      "p95": 1.25
    },
    "patch_write_attempts": {
      "known": 36,
      "missing": 0,
      "total": 34,
      "mean": 0.9444444444444444,
      "p50": 1.0,
      "p90": 1.0,
      "p95": 1.0
    },
    "committed_patches": {
      "known": 36,
      "missing": 0,
      "total": 31,
      "mean": 0.8611111111111112,
      "p50": 1.0,
      "p90": 1.0,
      "p95": 1.0
    },
    "real_test_runs": {
      "known": 36,
      "missing": 0,
      "total": 18,
      "mean": 0.5,
      "p50": 0.5,
      "p90": 1.0,
      "p95": 1.0
    },
    "command_attempts": {
      "known": 36,
      "missing": 0,
      "total": 18,
      "mean": 0.5,
      "p50": 0.5,
      "p90": 1.0,
      "p95": 1.0
    },
    "approval_denials": {
      "known": 36,
      "missing": 0,
      "total": 0,
      "mean": 0.0,
      "p50": 0.0,
      "p90": 0.0,
      "p95": 0.0
    },
    "sandbox_failures": {
      "known": 36,
      "missing": 0,
      "total": 0,
      "mean": 0.0,
      "p50": 0.0,
      "p90": 0.0,
      "p95": 0.0
    },
    "protocol_false_verified_count": {
      "known": 36,
      "missing": 0,
      "total": 0,
      "mean": 0.0,
      "p50": 0.0,
      "p90": 0.0,
      "p95": 0.0
    }
  },
  "failures": {
    "patch_commit_failed": 3,
    "invalid_tool_arguments": 3,
    "real_test_not_executed": 18,
    "hidden_tests_failed": 5,
    "model_request_timeout": 1,
    "request_budget_exhausted": 4,
    "task_timeout": 13,
    "agent_interrupted": 13,
    "revision_or_journal_mismatch": 13,
    "supervisor_audit_required": 13,
    "patch_preview_failed": 1,
    "no_progress_budget_exhausted": 1
  },
  "operator_audit": {
    "yes": 18,
    "no": 0,
    "external_yes": 6,
    "not_user_manual_approvals": true
  },
  "request_latency_seconds": {
    "known": 307,
    "missing": 0,
    "total": 3736.8624567561783,
    "mean": 12.172190412886573,
    "p50": 7.587538999971002,
    "p90": 24.817519008182014,
    "p95": 33.584283120674044
  }
}
```
Token分布只对已知Usage计算，并保留missing数量。价格缺失，因此费用及单位成功费用null；null不是免费。逐报告耗时包括隔离/评分和审批等待，不含槽位间约300秒线程退出等待；完整记录区间见JSON的recorded_cohort_wall_seconds。API请求延迟单列。

## 可靠性边界

固定同一Harness/模型/配置，但后两轮受操作中断混杂，稳定性未验收；三轮至少成功一次覆盖是best-of-3经验覆盖，不是单次成功率。3次样本不足以证明稳定因果效果。Judge评分未变，未修改基线的隐藏失败不能归因为候选修复错误。
原始证据保留在standard/runs，每份finished含raw SHA；evidence-sha256.json覆盖全部归档证据。SHA是损坏检测，不是恶意宿主不可伪造证明。
