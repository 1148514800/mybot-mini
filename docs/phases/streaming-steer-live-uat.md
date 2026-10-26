# Streaming & Steer Provider UAT准备专题

未编号专题，不修改历史Phase Tag/ZIP。目标是在零真实请求授权下，准备未来八次物理请求的可审计Web验收；不是新的产品功能或真实模型成功结论。

## 概念与架构

一次逻辑请求可有多个Provider物理尝试；reservation必须覆盖SDK创建到流关闭，而不在返回AsyncIterator时过早结算。scripts.streaming_steer_uat.adapter在原RuntimeAccounting中观察原样Chunk，SQLite Ledger复用原持久门并独立1/4/1/2额度。prepare记录源码、配置、Fixture与inode，clean preregistration commit后唯一freeze。server默认NOT_GRANTED，先验授权再接触配置/DB/SDK。

正式create_app、ChatRuntime和原AgentLoop不变；UAT进程专用Registry工厂仅收紧模型工具，R02只有原生read_file/list_files。Steer队列、工具未执行配对、后续准入、语义遵从分别验收。R02/03/04每物理流首非终态Chunk后8秒屏障，只控制时序，不修改输出。首role Chunk与可见文本、服务SSE发出与浏览器DOM时间分别记录。

## macOS + uv

```bash
uv run python -m scripts.check_streaming_steer_uat
uv run python -m compileall -q scripts/streaming_steer_uat
uv run --no-project --with playwright python -m scripts.streaming_steer_uat.browser_probe --chrome '<Chrome路径>' --output '<新私有路径>/browser-isolation.json'
# 当前批次已唯一prepare/freeze并verify通过；不要重复prepare或freeze。只使用原Provider路径verify。
uv run python -m scripts.streaming_steer_uat.prepare verify --provider-config '<prepared.json内原配置路径>'
```

## 案例、验证和限制

四个真实Case依次文本协议/UX、工具Steer、无下一步不应用、取消清理；当前全部LIVE BLOCKED。新增30项Mock专项，加相关217项去重通过及真实Chrome双身份探针。没有调用真实Provider；部署是否支持Streaming/include_usage、DOM体验和语义遵从尚未验证。

本专题不改生产Streaming/Steer，不重做Memory/Pin/决定来源。与上一阶段区别是独立持久额度和真实场景预注册，不是合成结果当作Live评分。最重要的常见错误是提前结算迭代器、把queued当applied、把空role当首Token、把屏障延迟当网络延迟，以及未经新授权启动服务。
