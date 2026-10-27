# SDK legacy representation

实际uv.lock与安装环境：openai2.32.0，Python3.12.14。使用AsyncOpenAI+httpx.MockTransport的原始SSE字节，通过SDK正式迭代解析，未调用Provider。ChoiceDelta.function_call声明Optional[ChoiceDeltaFunctionCall]；后者name、arguments均Optional[str]且默认None。

|原始字段|实际解析|bool|fields_set / extras|
|---|---|---|---|
|不存在|None|false|delta不含function_call|
|null|None|false|delta显式含function_call|
|{}|SDK模型，两个字段默认None|true|空fields_set、0extra|
|name/arguments均null|SDK模型，两字段None|true|两个显式字段、0extra|
|两字段均空字符串|SDK模型，两字段空串|true|两个显式字段、0extra|
|非空name或arguments|SDK模型，保留字符串|true|不能视为空|
|未知额外字段|SDK模型，model_extra保留|true|即使两已知字段None也不是语义空|
|外层字符串或非法name数字|SDK permissive构造保留错误类型|依值|字段注解不能代替运行时验证|

完整脱敏probe元数据见sdk-probe.json。每个比较只有1次Mock HTTP。默认构造流程为缺失Optional填充None，{}与缺失字段的Python表示不同；空模型的对象真值不是函数语义。额外字段不能由默认值填充而被忽略。诊断不导出函数名/参数/额外字段值。SDK未来版本行为可能不同，锁版本回归不可替代新版本验收。
