# 失败分析

## T02：负零格式未规范化

实际 calculations.line_subtotal 对 Decimal('-2')×0 量化得到 -0.00，service 的 format(...,'f') 保留符号。冻结 README/预注册已明确零数量含负单价须为 0.00。公开4项测试未覆盖此边界，故 Agent 自测与 Controller verified 仍成立，独立 Task FAIL。不是多文件入口绕过、Patch 未落盘或环境 metadata 故障。独立断言首次失败后其余断言未达；没有追加执行用于补分。

## T03：引用失效、预算回退与输出截断

第3轮真实摘要请求 id21（1515 Token）合法并经过裁剪应用。第4轮 id23（2367 Token）HTTP成功、finish_reason=stop，但 decisions 引用“界面先以命令行设计为主；图形界面留作以后可选。”并非所指第2轮 assistant 原文的精确子串（原文“交互形态：先以命令行设计为主；图形界面留作以后可选。”）。离线按已持久化请求/响应比对可定位该引用不合法；运行时仅提供通用 fallback_invalid_or_failed_response，不能把HTTP返回算语义成功。安全校验拒绝该摘要并规则回退。

第5轮 compaction 状态为 fallback_token_budget，无新增摘要 reservation/HTTP。此为冻结 Token enforce 门，不是全批34或T03物理上限耗尽；该轮具体未发送摘要请求未持久化，不能编造精确 Token。最终模型使用规则摘录，坦承依赖压缩历史，却丢失已定字典序规则。主回复 id25 在固定700输出Token处 finish_reason=length，未完成第5/6板块，EXIF时区、缓存持久化、撤销日志/崩溃恢复及明确未实现清单未完整输出。真实摘要发生、一次应用不等于端到端保真成功。回退未触发越权操作或虚构实现。

T02工具结果曾出现 current_clipped=true，作为背景记录，不能据此断言负零缺陷由裁剪导致。T03第4轮“记忆分开保存”属含糊措辞，实际没有持久化摘要或文件变化，不作已完成实现的证据。

T01无合同失败。批次无鉴权/网络错误、未知命令、安全越界、execution_uncertain、账本异常或清理不确定。无补跑、重建Fixture、改预算或事后修改验收条件。旧UAT 1/6保持不变。
