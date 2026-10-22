# 失败分析

严格失败保留在分母；不按Hidden Pass自动改判。下方跨组计数仅分类故障，不计算自然故障率；自然组和受控组分母另列。

{"hidden_test_failure": 2, "patch_failure": 1, "missing_current_revision_test_evidence": 1, "model_request_budget": 1}

- 01-config-default-001: 原始failure=public_tests_only，Agent=verified，Judge=hidden_fail；Patch元数据=[{"success": false, "error": "invalid_arguments", "patch_preview": true, "patch_write": false, "patch_committed": false, "patch_failure_phase": "validation", "patch_failure_state": "preflight_failed", "patch_safe_to_retry": true}, {"success": true, "error": null, "patch_preview": true, "patch_write": false, "patch_committed": false, "patch_failure_phase": null, "patch_failure_state": null, "patch_safe_to_retry": null}, {"success": true, "error": null, "patch_preview": false, "patch_write": true, "patch_committed": true, "patch_failure_phase": null, "patch_failure_state": null, "patch_safe_to_retry": null}]。
- 06-timezone-day-001: 原始failure=patch_failed_without_safe_recovery，Agent=blocked，Judge=hidden_fail；Patch元数据=[{"success": false, "error": "invalid_arguments", "patch_preview": false, "patch_write": true, "patch_committed": false, "patch_failure_phase": "validation", "patch_failure_state": "preflight_failed", "patch_safe_to_retry": false}]。
- 09-validation-chain-001: 原始failure=None，Agent=edited_unverified，Judge=hidden_pass；Patch元数据=[{"success": false, "error": "invalid_arguments", "patch_preview": true, "patch_write": false, "patch_committed": false, "patch_failure_phase": "validation", "patch_failure_state": "preflight_failed", "patch_safe_to_retry": true}, {"success": true, "error": null, "patch_preview": true, "patch_write": false, "patch_committed": false, "patch_failure_phase": null, "patch_failure_state": null, "patch_safe_to_retry": null}, {"success": true, "error": null, "patch_preview": false, "patch_write": true, "patch_committed": true, "patch_failure_phase": null, "patch_failure_state": null, "patch_safe_to_retry": null}]。
- 11-parse-convert-001: 原始failure=public_tests_only，Agent=verified，Judge=hidden_fail；Patch元数据=[{"success": false, "error": "stale_file_hash", "patch_preview": true, "patch_write": false, "patch_committed": false, "patch_failure_phase": "preflight", "patch_failure_state": "preflight_failed", "patch_safe_to_retry": true}, {"success": true, "error": null, "patch_preview": true, "patch_write": false, "patch_committed": false, "patch_failure_phase": null, "patch_failure_state": null, "patch_safe_to_retry": null}, {"success": true, "error": null, "patch_preview": false, "patch_write": true, "patch_committed": true, "patch_failure_phase": null, "patch_failure_state": null, "patch_safe_to_retry": null}]。
- 13-forced-failover-coding: 原始failure=model_request_budget，Agent=budget_exhausted，Judge=hidden_pass；Patch元数据=[{"success": false, "error": "stale_file_hash", "patch_preview": true, "patch_write": false, "patch_committed": false, "patch_failure_phase": "preflight", "patch_failure_state": "preflight_failed", "patch_safe_to_retry": true}, {"success": false, "error": "invalid_arguments", "patch_preview": true, "patch_write": false, "patch_committed": false, "patch_failure_phase": "validation", "patch_failure_state": "preflight_failed", "patch_safe_to_retry": true}, {"success": false, "error": "invalid_arguments", "patch_preview": true, "patch_write": false, "patch_committed": false, "patch_failure_phase": "validation", "patch_failure_state": "preflight_failed", "patch_safe_to_retry": true}, {"success": true, "error": null, "patch_preview": true, "patch_write": false, "patch_committed": false, "patch_failure_phase": null, "patch_failure_state": null, "patch_safe_to_retry": null}, {"success": true, "error": null, "patch_preview": false, "patch_write": true, "patch_committed": true, "patch_failure_phase": null, "patch_failure_state": null, "patch_safe_to_retry": null}]。

脱敏Trace没有原始Patch参数，不能恢复正文、确认具体非法字段或证明Preview/Write参数逐字段相同。只有明示错误与阶段可直接归因。

目录探索/文件哈希额外命令可直接观察（审批审计），但不能单凭工具名称确定全部探索无必要，不把猜测计作失败根因。当前提示没有完全消除额外探索。

Hidden Pass但Strict Fail：自然组1例；实际Controller/预算原因见逐例数据。若存在仍保留失败，不回写旧报告。

下一阶段可离线研究上下文中重复探索与证据收尾提示；任何新策略或预算都需新版本、新冻结组，不能通过自动完成回复、跳过审批或改变Judge抬高成功率。

## 可直接确认的专项失败

- timezone-day-001：正式Patch在validation阶段invalid_arguments，preflight_failed，safe_to_retry=false；Patch未提交。脱敏证据无法确定具体非法字段，不把它推断为磁盘发布失败。
- validation-chain-001：15请求、6次命令，Controller test_runs=3/test_passes=0、last_verified_revision=null，最终missing_current_revision_test_evidence；最后一次python -c本地测试命令虽返回成功，但不是原Harness认可的测试runner，不能伪造Revision证据。公开Judge与隐藏Judge均通过不改变Strict Fail。原failure字段为null是现有分类局限，本报告依据Controller字段保留失败，未来可离线补充分类。
- forced-failover-coding：首次本地注入后11次真实GLM请求；出现1次stale Preview、2次validation invalid_arguments Preview，随后Preview/Write成功。首次测试命令失败，第二次真实unittest取得Revision1/1证据时已耗尽12次物理预算，下一请求被拒绝；不是故障切换失败或Patch发布不确定。不能假设加一次请求必然成功。
- config-default-001、parse-convert-001：Agent verified而Judge hidden_fail；具体隐藏断言未读取，不能仅据脱敏Trace解释每个隐藏失败的精确输入或根因。

自然组失败分类：hidden_test_failure 2、patch_failure 1、missing_current_revision_test_evidence 1。受控组单列model_request_budget 1，包含原始预算失败分母。

## 重复动作与自动重放的边界

自然组repeated_actions计数均0；受控组为1。它是模型动作重复计数，不应隐去，也不能将其等同于Failover客户端自动重放工具。首次注入发生在任何工具之前；备用11次连续使用coco2，13个Attempt的Tool Call IDs均配对，正式Patch没有重复发布。没有客户端自动重放证据，但不声称模型从未重复无效探索或失败Preview参数。
