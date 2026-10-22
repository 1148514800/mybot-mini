# 失败分类规则 coding-failure-v2

failure_reason 现在调用 failure_classification，后者返回 version/category/source。新 Benchmark 结果同时保留 failure 字符串和 failure_classification。只解释结果，不修改 Controller、Judge、strict_success 或任何历史文件。

优先级：

1. runtime_error（包括 provider_error）→ runtime。
2. approval_denials / sandbox_failures → security。
3. Controller max_*：max_model_requests→model_request_budget；max_task_seconds→task_timeout；max_no_progress→repeated_action_loop；其余→tool_budget。
4. 无效/未评分 Judge 及文件、Index、Journal 违规→judge。
5. blocked 且有停止原因→controller。
6. 非 verified：edited_unverified 或 missing_current_revision_test_evidence→同名类别；取消、不确定、预算终态各保留明确分类；即使 Judge 的 verified_repair_success 为真，也不能返回 null。
7. verified 且 Judge repair success→null；verified + hidden_fail→public_tests_only；无修改与其余错误保持原分类。

历史 Case09：null→missing_current_revision_test_evidence / controller。其余12条类别不变。自然 Strict 8/12、受控Strict 0/1不变；不对原报告再评分。新派生文件显式列出原严格结果，并固定原 raw 哈希。Hidden状态来自已有脱敏报告，未打开隐藏断言。

回归包括真实证据缺失、强制矛盾的 unverified+Judge成功、verified+Hidden Fail、provider_error、请求预算和取消；分类函数不变更输入对象。
