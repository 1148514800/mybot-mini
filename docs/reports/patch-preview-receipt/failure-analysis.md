# 失败分析与对照口径

历史证据只读使用：前轮 [comparison.json](../tool-verification-live-ab/comparison.json) 两组 Strict 均为 3/4。bucket Candidate 成功 Preview 后 argument_parsing invalid_arguments，其原始参数、字段与具体意图 unknown；reservation Baseline 正式 Write 在 validation invalid_arguments。未恢复任何未保存参数，未修改旧私有测试或以其答案优化本实现。前轮请求 28 vs 32 的差包含提前失败，不视为节费证据。

本轮合成条件在脚本 SCENARIOS 中固定，12 条件 × 两组全部保留：正常、多文件、复杂 Unicode/引号/转义文本、二次生成 changes 破损、stale、权限变化、取消、工具预算、Write 预算、敏感路径、破损确认、发布后并发冲突。它们是公开构造的协议 fault injection，不是 12 个独立生产样本。两组同任务、同预算，固定先 Legacy 后 Receipt；不会估计模型分布或顺序效应。

Receipt 在二次生成 changes 破损条件获胜，因为模型无需再生成该正文；在权限变化条件额外拒绝。Legacy 未将 Preview 版本绑定到 Write，按提交时元数据安全保留当前 mode，所以可以继续；新协议的拒绝是更保守的 Preview 一致性，不能当作两组都失败，也不能隐藏该退化。正常、多文件、复杂文本两组通过。stale 两组没有提交，但 Legacy 的原 safe_to_retry 可继续有限后续测试，Receipt 失败立即停止；取消、两类预算、敏感路径、破损确认、不确定发布均未被 Receipt 放宽。回滚不确定两组各 1。

总计每组实际成功提交 4/12，正式提交尝试 8 次，条件提交率 4/8；其中损坏 JSON 的一次意图仅由本轮控制脚本已知，实际 Controller 仍不猜 raw 意图。分母包括失败、取消和预算耗尽。参数错误 Legacy 2、Receipt 0；Controller verified 与合成公开合同完成均为 4/12。工具实际执行 25 vs 24，合成逻辑/物理请求 33 vs 31，全部真实模型 HTTP 为 0。请求差混有更早安全停止及不同失败轨迹，不能解释成等质量成本改善。

原 `coding_campaign.strict_success` 必须接受 mode=live，并要求真实 Judge 的 hidden_pass 及完整安全证据。这里没有 Live 或私有 Judge；原 Strict 原函数返回 false，正式 Strict 计数均 0，strict_eligible=false。单列 synthetic_contract_success=4，绝不把公开合成合同通过重新命名为 Strict。原评分函数与私有 Judge 没有修改。

诊断区分 malformed_receipt、unknown_receipt、expired_receipt、consumed_receipt、wrong_attempt、stale_file_hash、metadata_changed、patch_write_disabled、write_failed、cleanup_uncertain。只复制白名单；未确认的 parser 意图/一致性为 null。unknown receipt 可能是伪造、被新 Preview 撤销、其他实例或进程重启，不能推断原调用者意图。墓碑仅保留一个摘要，较旧失败可退化为 unknown，不恢复旧正文。

剩余限制：供应商 Schema 支持、模型能否选择正确 Receipt、超长上下文裁剪导致 Receipt 不完整、TTL 内的高延迟、真实自然 fallback/取消分布均未 Live 验证。安全停止可能减少完成率；没有真实成功率或费用改进结论。
