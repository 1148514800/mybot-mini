# Original R01 evidence and limits

ORIGINAL_R01_ROOT_CAUSE: UNKNOWN

输入基线2b08360ee87aba28a9935f8a2b06fae2467883b4，原报告保持不变。没有原始328块完整结构，不能精确重放原响应；不能把本轮重复finish合成样本等同真实原因。

|顺序|事实|证据等级|
|---|---|---|
|1|原Ledger在SDK发送前reservation|账本1行＋发送路径代码；具体先后由代码推导|
|2|HTTP发送一次|原HTTP observer和资源记录直接证明|
|3|SDK首Chunk在约2.344s，无文本|原first-chunk直接证明|
|4|后续有文本，累计328块，真实DOM预览|原stream、SSE、浏览器证据直接证明|
|5|observer记录finish_reason=stop|直接证明见到过该字段，不证明自然EOF|
|6|consumer最终provider_error，停止正常处理|终态直接证明；具体校验拒绝点未证明|
|7|wrapper记录GeneratorExit、eof=false|直接证明；它是否由某具体协议拒绝触发，未证明|
|8|SDK wrapper close=true|observer直接证明|
|9|reservation failed，Usage全null|原Ledger直接证明；不等于零账单|
|10|AgentLoop/Web返回provider_error，正文前有未完成告警|原settled和持久事件直接证明；调用顺序代码推导|
|11|原UAT自动HALT=protocol_or_runtime_failure|Ledger＋settled回调代码证明；Case仍running|
|12|launcher SIGINT后等待25秒超时，之后PID/端口/Lease释放|原操作员证据直接证明；退出方式/退出码未证明|

GeneratorExit不是供应商网络断开证据；它也可能来自本地主动停止消费后的生成器终结。stop不是EOF证据。新的结构诊断可以让未来相似故障指出真正的拒绝代码，但不能倒填原R01缺失的数据。

原操作员在SIGINT前已调用page.close；不能仅凭SSE源码循环就认定当时存在活动连接。当前合成分别证实SSE drain依赖与继承TTY时launcher信号不转发，两者是可复现机制，原故障中各自影响仍UNKNOWN。

原冻结prepared/freeze、原私有两库仅只读检查；HALT、1次请求、R01 running均不改。新源码不匹配旧freeze是预期，禁止更新旧freeze来继续剩余7次。
