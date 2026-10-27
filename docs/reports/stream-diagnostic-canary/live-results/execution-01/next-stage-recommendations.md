# Next stage after the single failed canary

本批次1/1额度已用尽，Case failed、HALT保留。禁止重启D01、重发消息、复用旧7次、继续Steer或为Usage额外请求。新修复应从单独开发任务开始，不修改本次冻结资产。

优先离线检查legacy function_call对象的真值判断；为诊断增加安全的presence/type/字段是否空元数据，并将其与真正“终态后负载”的代码分类分开。现有ring缺此字段，不能准确还原供应商输出或SDK默认值作用。不要先为追求PASS放宽协议或移除include_usage。

补充SDK schema/终态空对象的MockTransport回归，分别验证真实函数调用、空legacy对象、终态空负载和标准Usage trailer；确认不会执行不完整工具或扩大权限。这是建议，不是本轮已实施修复。

独立保存观察Usage与可信结算Usage的差异，并改进动态截图遮蔽方式。正常exit0清理已经取得本次真实证据，但不保证所有关闭场景。未来真实兼容验收必须新授权、新冻结批次；D01失败不倒填旧R01缺失证据。
