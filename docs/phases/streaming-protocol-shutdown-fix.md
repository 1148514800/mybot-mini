# Streaming协议诊断与服务关闭修复专题

未编号工程专题，不创建/移动历史Tag或ZIP。本阶段真实模型授权0；保持原Live失败与HALT。

## 学习目标与调用流程

正式Web create_app → ChatRuntime → AgentLoop → RuntimeAccounting/ProviderFailover → consume流解析。模型文本可以显示为临时预览，但只有合法终态、SDK自然EOF与关闭确认才能成为可信完整结果。GeneratorExit常是迭代器清理的后果，不能作为网络断开根因。

streaming.py中的StreamErrorCode和StreamProtocolError记录固定分类，consume的8块结构ring帮助区分拒绝阶段，不记录内容。记录挂在单次物理accounting record；SSE只传固定错误码，Web用本地文字“协议结构不兼容／流中断／关闭状态未知”展示，完整诊断不进入模型上下文。

server.py中的有限SSE请求打破Uvicorn先等待HTTP、再退出lifespan的循环依赖。浏览器EventSource按Last-Event-ID与250ms retry重连，最终状态由认证GET恢复；不重发模型任务。runtime.py的同Task清理deadline保留MCP cancel scope所有权，close只清理现有任务，不解除HALT或审批。

scripts/local_web_process核对自己子进程的PID/UID/出生时间/命令/cwd/端口后才能补发SIGINT，用于继承TTY时uv未转发的情况。此模块不是模型工具，不扩大Agent命令权限。

## macOS + uv 操作

```bash
uv run python -m scripts.check_stream_protocol_diagnostics
uv run python -m scripts.check_stream_shutdown
uv run python -m scripts.check_stream_sse_lifecycle
uv run python -m scripts.check_phase
uv run --no-project --with playwright python scripts/stream_protocol_browser.py
uv run python -m compileall -q mybot scripts
node --check mybot/web/static/app.js
git diff --check
```

Chrome脚本只创建0700临时profile与MockTransport服务。不要运行原Live server，不要改旧freeze，不使用剩余7次额度。

## 实际案例与边界

标准400多块流通过；stop后重复finish精确标stream_duplicate_finish；stop后内容标stream_after_finish_payload，均不返回工具。原真实328块没有完整结构，ORIGINAL_R01_ROOT_CAUSE仍UNKNOWN。

旧SSE持连接会阻止退出的机制与继承TTY时launcher信号不转发分别合成复现。新真实Chrome A–G已验证协议错误、工具、Steer、HALT与恢复，具体证据在专题报告。全量回归结果在Acceptance提交时记录；Implementation阶段不得提前宣布全量完成。

与上一阶段变化是增加有界可观测性与可信关闭边界，没有放宽模型终态、删除旧断言或重跑旧Live。
