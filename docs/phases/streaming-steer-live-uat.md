# Streaming & Steer Provider UAT专题

未编号专题，不修改历史Phase Tag/ZIP。最初在零真实请求授权下准备八次物理请求的可审计Web验收；本轮授权执行结果另列于文末，不改原离线报告。

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

四个真实Case依次文本协议/UX、工具Steer、无下一步不应用、取消清理；离线准备时全部LIVE BLOCKED，原结论保留在准备报告。新增30项Mock专项，加相关217项去重通过及真实Chrome双身份探针。当时没有调用真实Provider，部署协议、DOM体验和语义遵从未验证。

本专题不改生产Streaming/Steer，不重做Memory/Pin/决定来源。与上一阶段区别是独立持久额度和真实场景预注册，不是合成结果当作Live评分。最重要的常见错误是提前结算迭代器、把queued当applied、把空role当首Token、把屏障延迟当网络延迟，以及未经新授权启动服务。

## 本轮真实执行与学习结论

收到新的GRANTED_8_REQUESTS后，原冻结预检通过并完成动态Chrome双身份隔离。真实R01消费328块并在终态前显示预览；首空Chunk约2.344s、首内容2.356s、浏览器提交到DOM预览3.461s。没有时钟关联，SDK到DOM差UNKNOWN。

R01最终provider_error、eof=false，虽observer见stop，也不能当完整成功。Ledger自动HALT，物理1/8、DeepSeek1/GLM0/摘要0，Usage未知、cost=null；R02–R04安全BLOCKED，无补跑。具体consumer拒绝分支没有被记录，GeneratorExit只说明上游停止消费，不能反推唯一根因。

正常关闭自己的uv launcher等待25秒超时；最终独立核实进程消失、端口/Lease释放及Chrome/profile清理，但退出码未知、Case仍running，Cleanup不能判PASS。新Live结果见[独立报告](../reports/streaming-steer-live-uat/live-results/execution-01/acceptance-report.md)。原源码/Fixture/hash/inode保持，不为诊断再调用Provider。

本轮学习重点是：终态字段与可信完成分离，正文hash一致与完整性分离，最终资源释放与正常退出码分离。下一阶段先补脱敏错误可观测性与Mock验证，再考虑新的独立授权Live；不能修复旧账本制造成功。
