# 通用 Provider Failover Chain

`llm.provider` 选默认项，`llm.providers` 保持 JSON 声明顺序。例如依次声明 alpha、beta、gamma，而默认为 beta，一次模型响应的尝试顺序为 beta → gamma → alpha，各项最多一次。成功项在当前 Agent 任务后续模型步骤保持；下一条独立用户任务从默认项重新开始，CLI 无须重启。运行时不写回配置。

每项提供自己的 `api_key`、`base_url`、`model`。原任务的工具、审批、Patch、上下文与预算配置共享，不随 Provider 扩权。配置示例：

```json
{
  "llm": {
    "provider": "beta",
    "request_timeout_seconds": 90,
    "providers": {
      "alpha": {"api_key": "YOUR_ALPHA_KEY", "base_url": "https://alpha.example/v1", "model": "model-a"},
      "beta": {"api_key": "YOUR_BETA_KEY", "base_url": "https://beta.example/v1", "model": "model-b"},
      "gamma": {"api_key": "YOUR_GAMMA_KEY", "base_url": "https://gamma.example/v1", "model": "model-c"}
    }
  }
}
```

替换占位凭证，或删除未配置项。所有声明项必须含非空的三字段；无效配置在构造 Client 前拒绝。兼容旧的顶层默认凭证配置，以及现有双 Client 的评测构造接口；普通应用不再依赖 coco/coco2 名称。没有修改真实 config/config.json 或依赖文件。

## 切换与停止

可切换：连接/网络故障、请求超时、HTTP401/403/404/408/429及所有5xx；原生消费者确认安全关闭后的流传输中断、流等待超时或缺失终态。所有 Provider 失败后，返回只含 Provider 名称和固定分类的汇总，不输出完整 SDK 异常、凭证或 URL。

不可切换：普通参数/Schema错误、宿主错误、工具权限拒绝、预算/安全门拒绝、用户 Stop，或流关闭无法确认。API403 表示提供方请求拒绝；工具权限拒绝仍由原生权限机制处理，二者不混淆。

每个 Provider 都获得完整 `request_timeout_seconds`，覆盖打开及消费当前响应，删除原 `/2` 整流截止。AgentLoop 的逻辑窗口为所有 Provider 窗口之和加各自至多3秒关闭余量，并取 CodingTaskController 剩余任务时间的较小值；Web 外层任务截止也保持有效。Stop/外层截止的 CancelledError 不被当作 Provider 超时。宿主请求准入或预览回调超时也不当作网络故障。

## Streaming 和执行边界

原生 consume 在合法终态、EOF和关闭验证后才交付完整工具调用。链在 dispatch 内运行，此时当前响应没有机会进入工具执行循环。因此失败响应的部分文本/工具参数不会与下一 Provider 的响应拼接，也不会被执行。确认 SDK/生成器关闭后，发送空的 model_stream_discarded 事件，CLI/Web 临时预览撤销，再重新生成同一模型响应。

此前模型步骤已经完成的工具调用和结果保留在请求历史中，不重新派发。工具执行阶段的失败发生在链外，不会触发自动重放。协议结构/非法工具参数拒绝保持原规则；关闭不明时停止，不能强行切换。

## 计数、预算与脱敏

每个物理调用都经过原 dispatch、TokenCounter、HTTP hook 和原生 fallback 预算门，包括失败调用。Provider/模型使用当前配置，未知 Usage 保持 null，已报告小计与总数分开；不为补 Usage 额外请求。SDK retries=0。

Web、Streaming 预览、CLI 最终回复和切换日志覆盖所有链中 Provider 的 API Key 脱敏；错误汇总只含固定分类。安全关闭诊断保留原始分类，本地 Provider 截止额外记录 provider_deadline_expired，不把用户取消伪装为超时。

## 离线验证

新增 `scripts/check_provider_chain.py` 19项：首项成功、超时切换、第三项成功、全链失败、默认项回绕及各自凭证、任务内保持/新任务重置、HTTP分类、宿主错误、流关闭/片段丢弃、关闭失败、非法协议、Stop、已完成工具不重放、三模型Key脱敏、Coding预算/任务时间上限、真实SDK MockTransport计数等。

```bash
uv run python -m unittest scripts.check_provider_chain scripts.check_provider_failover scripts.check_streaming_failover scripts.check_runtime_accounting scripts.check_stream_protocol_diagnostics scripts.check_stream_legacy_function scripts.check_streaming_steer_web scripts.check_web_ui scripts.check_token_budget -q
uv run python -m compileall -q mybot scripts
node --check mybot/web/static/app.js
git diff --check
```

本轮相关专项243项通过。旧半超时、仅临时HTTP错误、跨任务粘滞和中途失败禁止回退的断言按本轮明确的新合同更新，原安全关闭/Stop/预算断言保留并扩展。未运行完整Benchmark，未创建Canary/批次/冻结，真实付费请求0。C02失败报告、账本、原14次余额均未使用或改写。真实部署兼容性未在本轮验证。
