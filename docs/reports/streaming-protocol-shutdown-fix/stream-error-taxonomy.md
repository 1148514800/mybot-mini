# Bounded stream diagnostics

mybot.agent.streaming.StreamErrorCode定义固定错误枚举。StreamProtocolError只接受枚举；不把任意异常正文变为错误代码。正常流error_code=null。

|代码|分类|
|---|---|
|stream_choices_invalid / stream_choice_index_invalid|choices结构、单Choice/index不合法|
|stream_role_invalid / stream_content_type_invalid|role或content类型不兼容|
|stream_after_finish_payload / stream_duplicate_finish|终态后继续语义负载／重复终态|
|stream_tool_fragment_invalid / stream_tool_arguments_invalid / stream_tool_index_gap|工具片段、严格JSON或索引连续性失败|
|stream_provider_error_frame|显式Provider错误帧，正文不保留|
|stream_transport_interrupted|SDK迭代的APIError、HTTPError、OSError；不保存原始异常|
|stream_local_buffer_limit|本地32K文本或工具缓冲上限|
|stream_terminal_missing|自然迭代结束后缺少已知终态|
|stream_user_or_caller_cancelled|调用方取消；仅靠CancelledError无法判断用户Stop还是外层deadline取消|
|stream_local_timeout|直接TimeoutError；外层asyncio.timeout由调用方区别timeout与用户Stop|
|stream_host_failure|预算、存储、未知宿主异常等向上抛出，不转成普通Provider结果|
|stream_close_unconfirmed|关闭失败／超时；StreamCleanupError向上抛出，保留primary_error_code|

每物理record最多8块结构环形记录：chunk_index、choices_count、delta/role字段是否存在、content固定类型名及长度、tool_calls数量、允许列表finish值。流级保存随机stream_id、处理阶段、观察计数、终态次数、是否见文本、natural_eof、close_called/closed和固定来源类别。

不保存原文、工具参数/名字/ID、完整Chunk、Prompt、原始SDK异常、私有路径、Cookie/CSRF或授权头。未知finish值只显示unknown，Python类名不直接透出。SSE/普通状态只扩展固定error_code，不广播整个结构ring。

协议验证与SDK迭代异常路径分开。未知宿主异常（包括原BudgetStop、StoreError）关闭资源后原样向调用方抛出，不降格为可恢复provider_error；原首Chunk前/后Failover边界保持。OSError本身不能证明远端断网，类别表示迭代异常而非因果归责。notify/持久化回调异常也不作为Provider错误处理。
