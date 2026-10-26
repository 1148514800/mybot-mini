# Streaming & Steer v1 学习专题

未编号专题，不创建或移动历史Phase Tag/ZIP。报告见[Streaming & Steer验收](../reports/streaming-steer-v1/acceptance-report.md)。

## 目标与Agent概念

Streaming是一次真实请求的增量消费，预览不是持久消息。Steer是同Turn的下一步骤输入，不是另开Turn的follow-up，也不是授权。queued、applied、模型遵从与业务正确性必须分别判断。

## 架构与核心调用

Web ChatRuntime持有WorkspaceLease和Turn；AgentLoop在原_request_model设置stream标志和观察器。RuntimeAccounting.dispatch在同物理记录内创建SDK迭代器并consume。streaming.consume按index组装工具，只在可信终态交付；SafePreview跨Chunk缓冲脱敏，finally有界关闭流。ProviderFailoverClient用PROGRESS区分首Chunk前与之后的错误。

SteerInbox.submit校验宿主用户、Turn、容量与幂等，写schema v2审计。原Loop在工具前检查pending，补齐未执行结果；下一步重建请求、复查Token与Controller预算，物理准入后resolve(applied)。TaskContract和Pin仍使用原来源，不改权限或原消息。

Web以有界绝对预览快照、事件sequence、Turn/Stream ID和revision恢复SSE，不逐Token做完整GET。安全Markdown与停止/审批保留。重启只恢复审计，不重新消费流或重放Steer。

## macOS + uv

```bash
uv sync --frozen
uv run python mybot/main.py
uv run python -m scripts.check_model_streaming
uv run python -m scripts.check_streaming_failover
uv run python -m scripts.check_steer_inbox
uv run python -m scripts.check_streaming_steer_web
uv run python -m scripts.check_phase
uv run python -m scripts.check_persistent_session_uat
uv run python -m scripts.check_source_aware_uat
uv run python -m compileall -q mybot scripts
node --check mybot/web/static/app.js
uv run --no-project --python 3.12 --with playwright python scripts/streaming_browser_acceptance.py
```

默认web.streaming.enabled=false和web.steer.enabled=false。浏览器合成驱动自动创建私有临时库/workspace/profile并用8899 MockTransport服务；不加载真实Provider凭证。Playwright不加入生产依赖。

## 案例、变化和限制

公开合成A–H覆盖终态前中文/Markdown、跳过未启动工具、无下一步、断流、真实网络重连、审批拒绝、重启和停止。新增97项专项，完整回归计数见报告，不重复计入定向执行。实际浏览器8次SDK Mock HTTP，真实DeepSeek/GLM/摘要/Judge0。

与上一专题相比，只增加运行中交互，不重建来源/决定/持久会话。原Pin和TaskContract不因Steer改变；旧历史的语义问题不自动修复。常见问题：长行未展示可能是保守隐私策略；Usage未知不是0；applied不是模型成功；无下一步必须新消息显式提交；旧写者需协调升级。
