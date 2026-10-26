# Streaming protocol

显式启用的Web Agent请求发送stream=true和stream_options.include_usage=true。通过SDK真实AsyncIterator接收数据，完成前即可产生安全预览；没有完整回复后的假字符播放，没有第二次完整请求或不支持流时的隐式重试。

单choice文本协议，delta.role只允许assistant/空；content逐段累加。finish_reason=stop且有文本无工具为complete；tool_calls还需完整组装验证。length→output_truncated，content_filter→content_filtered，stop空文本→empty_response，缺失/未知终态→response_unconfirmed，损坏/断流→provider_error。用户取消→cancelled；进程死亡由原历史恢复标interrupted。流式结果显式携带stream_delivery，不能被旧无finish工具兼容分支升级。

[Chat Completion流式参考](https://developers.openai.com/api/reference/resources/chat)允许末尾Usage Chunk没有choices，且断流可能没有Usage。因此正常结束也不会用文字长度推断终态，缺失Usage保持null。只在供应商终态可信且未发生断流时采纳其Usage；不推算账单。cost=null。

文本缓存上限32768字符，工具片段总上限65536字符、最多16个调用；超大单片段在缓存拼接前拒绝或截断。预览上限8192 UTF-8字节，活动deque仍128项。无每Token SQLite事务。

finally关闭SDK stream，关闭等待上限3秒；失败或无法确认关闭抛StreamCleanupError，Web进入不确定安全阻止，保留Lease。取消和超时不执行部分工具，不自动续写；客户端SSE掉线只影响显示，不取消Agent。
