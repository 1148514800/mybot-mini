# D02 actual protocol evidence

consumer观察514块，recent_chunks仅保留507–514共8块。accepted finish_reason=stop，terminal_count=1，phase=terminal_validation，error_code/origin=null，natural_eof=true、close_called=true、closed=true、terminal_trusted=true。Web completed与正式持久哈希一致，具备本次完整性证据；没有只凭stop判PASS。

末块choices1、delta存在、role存在、空字符串content、tool_calls0。legacy_function_call_present=true、kind=object，name/arguments均string长度0、extra0、semantically_empty=true。新检查允许这个空负载并继续终态校验。已知SDK2.32.0对象真值不能代替字段内容；D02实际解析结果支持这项兼容修复。

没有原始Chunk/函数名/参数/extra键值副本。当前结构不能区分线上的JSON原本为空对象、含空字段还是SDK默认填充，不能反推出旧D01内容。非空legacy、非法结构、post-finish负载等的严格拒绝由原离线回归证明，本轮没有再调用真实Provider去制造这些异常。

观察Usage与可信Usage一致，但observer未保存其具体到达索引，不补写“独立Usage尾块”事实。自然SDK迭代终止及owner关闭已确认，不推断未记录的原始线格式细节。SDK→浏览器时钟不同，不相减。
