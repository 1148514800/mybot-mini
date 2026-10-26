# Synthetic protocol reproduction

ORIGINAL_R01_ROOT_CAUSE: UNKNOWN

以下是独立的可确定性合成场景，不能冒充原328块响应精确重放。39项协议专项覆盖以下矩阵，另有关闭11、SSE8项。

|场景|EOF|最终状态／诊断|可信完整|
|---|---|---|---|
|标准text + stop|是|complete / null|是|
|stop后空choices Usage|是|complete / null，Usage保留|是|
|stop后重复finish|否|provider_error / stream_duplicate_finish|否|
|stop后非空content|否|provider_error / stream_after_finish_payload|否|
|缺失/null/错误类型choices|否|provider_error / stream_choices_invalid|否|
|错误role|否|provider_error / stream_role_invalid|否|
|多Choice或错误index|否|provider_error / stream_choice_index_invalid|否|
|分块工具参数完整|是|tool_calls / null|可信工具结果，非自然语言完成|
|工具JSON不完整|是|provider_error / stream_tool_arguments_invalid，无工具|否|
|索引不连续／片段不合法|视拒绝阶段|tool_index_gap / tool_fragment_invalid|否|
|缺失终态|是|response_unconfirmed / stream_terminal_missing|否|
|finish=length|是|output_truncated|否（可信截断终态）|
|finish=content_filter|是|content_filtered|否（可信过滤终态）|
|首Chunk前网络异常|否|原异常上抛；transport代码，原Gateway可合法Fallback|否|
|首Chunk后网络异常|否|provider_error / stream_transport_interrupted，不Fallback|否|
|stop后网络异常|否|同上，不把stop当完整|否|
|正常stop但close失败|是|StreamCleanupError / stream_close_unconfirmed|否|
|SDK迭代提前正常结束且无finish|是|stream_terminal_missing|否|
|超本地32K|否|output_truncated / stream_local_buffer_limit|否|
|空Usage|是|合法终态可complete；账单Usage=null|是，费用未知|
|取消进入finally|否|CancelledError / stream_user_or_caller_cancelled，仍close|否|
|直接本地TimeoutError|否|原timeout上抛 / stream_local_timeout|否|
|401块合法长流|是|complete，无328块数量门|是|
|预算／StoreError／未知宿主错误|否|原异常上抛 / stream_host_failure，不能当Provider可恢复错误|否|

共享run_stream测试通过实际RuntimeAccounting＋Synthetic Client验证一次逻辑/物理记录、无Fallback和关闭确认；独立AsyncOpenAI MockTransport测试验证SDK标准Usage解析。真实Provider请求均0，不把Mock记账数当付费请求。原Streaming Failover12专项另验证首块前2物理尝试、首块后1物理尝试且无备用；旧33项流测试保持。

额外独立实验用未修改的原UAT BudgetClient/ObservedStream、全新可丢弃Ledger与SDK MockTransport，构造stop后重复finish：consumer精确记录chunk2/terminal_count2/stream_duplicate_finish，上游observer仍记录GeneratorExit/eof=false/close=true，物理Mock1且结算。见observer-reproduction-evidence.json。这证明诊断可识别真正本地拒绝原因，不证明原R01就是重复finish。
