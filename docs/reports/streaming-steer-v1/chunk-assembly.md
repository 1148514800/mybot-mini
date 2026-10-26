# Chunk assembly and tool safety

按tool_calls.index独立累积id、function.name和arguments。终态工具调用必须索引连续、ID非空且互异、函数名语法合法、参数复用现有parse_object验证为完整JSON对象（拒绝重复键、非有限数、过深/超量结构），且整体在缓存预算内。不同index的片段不混合；不会补全模型没有生成的括号或字段。

只有finish_reason=tool_calls且校验通过才返回规范化Tool Call。部分JSON、缺失finish、未知类型、重复ID、索引缺口、过长片段、断流和取消均不交付可执行工具集合。即使名称/JSON完整，仍必须经原Registry、工具可见集合、TaskContract、Controller、Patch Receipt和审批门，不能恢复旧权限。

Steer取消未启动调用时，保留原assistant.tool_calls，并为每个调用生成同ID、success=false、executed=false的not_executed_pending_user_steer结果。已开始的调用保持真实结果；不伪造成功、不声称回滚、不把已执行操作重标为未执行。后续请求维持所有工具配对。

专项覆盖交错index、中文/Markdown跨Chunk、工具名与JSON跨Chunk、无finish工具不走旧兼容成功分支、参数上限与关闭异常。浏览器B证明未进入工具执行路径；D证明部分工具片段断流后没有tool.started。
