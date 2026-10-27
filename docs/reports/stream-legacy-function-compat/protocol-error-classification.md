# Fixed error taxonomy and redaction

|情形|固定错误码|
|---|---|
|已知空legacy字段|无legacy错误，继续验证|
|真实legacy字符串负载或未知extra|stream_legacy_function_call_unsupported|
|legacy结构/字段类型不合法|stream_legacy_function_call_invalid|
|已接受终态后非空content/tool_calls|stream_after_finish_payload|
|重复finish|stream_duplicate_finish|
|缺少终态/网络中断/关闭失败|沿用原独立码，不伪造完成|

recent_chunks仍最多8块。新增legacy_function_call_present、legacy_function_call_kind、legacy_name_kind/length、legacy_arguments_kind/length、legacy_extra_field_count、legacy_semantically_empty。类型为固定词汇；长度饱和65536、extra计数饱和256。不记录name、arguments、未知extra键值、模型正文、Chunk、密钥或异常字符串。显式missing与null通过model_fields_set区分，SDK模型统一标object，不输出动态类名。

Web普通SSE只沿原安全预览和固定error_code通道，不新增ring或完整对象；UI把新码识别为协议不兼容，不直接显示内部字段。模型生成内容没有获得新的工具或确认权限。
