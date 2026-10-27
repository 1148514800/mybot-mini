# Independent D01 dimensions

|维度|结果|真实证据及范围|
|---|---|---|
|Protocol|FAIL|Chunk221、stream_after_finish_payload、protocol_validation；无自然EOF、无可信完整终态|
|Task Success|FAIL / unconfirmed complete|不将预览或已保存的带失败状态文本当成可靠六段完整答复|
|Workflow|FAIL；操作员流程完成|唯一DOM发送和关闭完成，但产品回复以provider_error结束|
|Safety / Integrity|PASS|冻结/权限/预算保持，0工具，1/1、无补跑，无execution_uncertain|
|UI Responsiveness|局部PASS|running期间真实预览，提交至可见2.500s；终态明确显示异常|
|Final Persistence Integrity|FAIL for trusted complete|持久回复有provider_error状态；不是可信完整模型回复，不能用有SQLite消息判PASS|
|Usage Compatibility|UNKNOWN|SDK观察480/219/699，未自然EOF；ledger结算全null，未核对账单|
|Diagnostic Coverage|PARTIAL|错误码/阶段/Chunk/ring/close齐备；缺legacy function_call安全结构字段，责任UNKNOWN|
|Clean Shutdown|PASS|正常wait exit0，SDK close、端口、Lease、数据库及进程退出独立确认|

失败后新HALT=diagnostic_failed保留。只有一个Live Attempt；页面初始空session不算额外Attempt。没有以关闭成功改变协议评分，也没有因拿到stop把失败改判。
