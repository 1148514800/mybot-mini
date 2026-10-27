# Streaming Legacy Function Call兼容与D02准备

未编号工程专题，不新建或改动历史Phase Tag/ZIP。

学习目标：SDK对象的Python真值与协议语义不同。Optional字段默认值不保证解析类型合法，Pydantic空对象也可能truthy。Agent必须在工具授权之前区分“无负载”“不支持调用”“结构错误”，不能因为兼容修复让模型取得新工具权限。

正式流程保持Web→ChatRuntime→AgentLoop→ProviderFailover→RuntimeAccounting→streaming.consume。_legacy只检查已知SDK模型/dict的name/arguments及extra；返回安全元数据和固定码。空对象继续正常终态校验，真实legacy负载拒绝，终态后负载独立拒绝。close/EOF/工具参数/预算边界保留。新增D02 harness复用私有账本身份/HTTP门、ReadRegistry和原生入口，以新Case、合同、workspace及两库隔离旧批次。

核心文件：mybot/agent/streaming.py、mybot/web/static/app.js；scripts/check_stream_legacy_function.py与legacy_stream_fixtures.py；scripts/stream_legacy_canary/与check_stream_legacy_canary.py；stream_legacy_steer_browser.py。前者生产分类，后者SDK字节/空对象及预算/浏览器合成验证；不读取旧私有模型Chunk。

macOS/Python3.12+/uv：`uv run python -m scripts.check_stream_legacy_function`；`uv run python -m scripts.check_stream_legacy_canary`；`uv run python -m scripts.check_phase`；`uv run python -m compileall -q mybot scripts`。Chrome使用临时`uv run --no-project --with playwright`，不修改生产依赖；具体入口及唯一冻结命令见报告预注册。

实际Synthetic：221块末尾空legacy对象自然EOF，带尾块则222块且Usage可信；同结构含真实函数名被拒绝。SDK2.32.0可把{}构造为truthy模型，不能用`if function_call`。D01原字段未保存，不能以Synthetic冒充原始重放。相较上阶段新增两种legacy码与结构元数据，没有重写流消费器或扩大权限。

当前验收、统计、冻结与限制见[专题报告](../reports/stream-legacy-function-compat/acceptance-report.md)。本轮真实请求0，D02须未来新的GRANTED_1_REQUEST；旧R01/D01不改判、不补跑。

最终验收：2051个去重unittest PASS（新增67），13个Chrome合成场景、7次自身服务exit0；真实模型0。D02已唯一prepare/freeze，源码SHA 06d53077c3f35985506c835b42d29fd8cd394aa7，verify通过、Attempt/reservation/HTTP均0。新Live须另有明确授权。
