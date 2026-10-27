# Explicit Synthetic regression

legacy_stream_fixtures只构造公开合成SSE，不读取旧D01。221 Chunk：220块文本，最后空content、tool_calls=[]、role=assistant、finish=stop，function_call={}；可选再加空choices Usage尾块。SDK将{}解析成truthy ChoiceDeltaFunctionCall，其已知字段None。

新专项34项均通过。无Usage版本221块可信结束、Usage未知；加Usage版本222块自然EOF且close确认，实际Mock字段7/9/16进入RuntimeAccounting可信Usage；含非空legacy函数名的同结构版本在221被明确拒绝，tool_calls=None，不执行工具。每个SDK样本只有1次Mock HTTP、1个物理记录。

其他覆盖：缺失/null/空/null字段/空串、wrong outer type（含false/0/空列表/空串）、wrong known type、extra包括值null、隐私哨兵不泄漏、长度/计数饱和、合法Usage尾块、终态后content/tool_calls、重复终态。原39项继续覆盖401+合法流、输出上限、非法工具JSON与close失败等，未删除断言。

这些结果只证明已知合成机制，不证明原D01实际字段为空，不计入真实模型请求。
