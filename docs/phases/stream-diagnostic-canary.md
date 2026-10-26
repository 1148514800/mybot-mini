# Streaming Diagnostic Canary：一次请求的可审计诊断

这是未编号工程专题，不创建或移动历史Phase Tag/ZIP。

目标是将“流显示过文字”与“协议完整、最终保存、服务正常退出”分开证明。预算不是模型自觉：SQLite预留在SDK创建之前提交，HTTP hook在发送之前计数；备用策略只能提出下一请求，不能扩大额度。Attempt在服务启动时唯一登记，失败不重置。

调用关系：plan定义完整合同；prepare复用指纹/私有存储能力；budget复用原身份、HTTP与结算门但独立1次限额；server通过原create_app/Runtime/AgentLoop/ProviderFailover；adapter透明观测真实SDK；mock用MockTransport而不加载真实Provider配置；browser用独立Chrome DOM操作并在EventSource打开时关闭自有服务。生产Streaming/Steer实现不变。

macOS/Python3.12+/uv运行：`uv run python -m scripts.check_stream_diagnostic_canary`。浏览器工具为临时`uv run --no-project --with playwright python -m scripts.stream_diagnostic_canary.browser --chrome <现有Chrome> --output <新的私有临时目录>`；所有HTTP被MockTransport拦截，不安装或替换用户Chrome。双profile探针复用scripts.streaming_steer_uat.browser_probe。

常见误区：stop不证明EOF；GeneratorExit不证明Provider断流；端口释放不证明exit0；Usage缺失不必然协议FAIL；被拒绝的备用准入不是第二次HTTP；合成PASS不证明DeepSeek兼容。原R01证据与HALT不可改判。

状态及准确统计见[验收报告](../reports/stream-diagnostic-canary/acceptance-report.md)。下一步仅在新授权GRANTED_1_REQUEST后verify并执行一次D01，不复用旧余量。
