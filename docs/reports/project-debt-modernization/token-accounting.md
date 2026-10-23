# Token 计量审计

实现：`mybot/agent/token_counter.py`（measure/policy/enforce）、ContextManager.prepare、RuntimeAccounting.request/dispatch、ProviderFailoverClient.create。配置与公式见 [Context](../../context.md)。完整可见 kwargs 在发送前再次计量，预处理视图和最终发送不是两个互不关联的计数器。输入受估算上限约束，无法适配的 System/用户/Schema 直接拒绝；回退时按备用模型重新判定，不能绕过更小窗口。

| 数值 | 精度/语义 |
|---|---|
| request_chars | 对可见 kwargs 的 JSON 字符计数，非服务端 wire 编码长度 |
| request_utf8_bytes | 同一 JSON 的 UTF-8 字节数 |
| local_tokenizer_tokens | null；没有可验证部署映射 |
| estimated_input_tokens | conservative_utf8_estimate_v1；不是数学上界 |
| provider_reported_* | 响应 Usage 原样非负整数；缺失为 null，不保证供应商账单无误 |
| exact_remaining_tokens / estimated_cost | null，未推断 |

旧 `ContextManager.count` 仍返回 messages/tools JSON 字符长度，旧 max_chars 语义与测试保持。新 request_chars 还包括 model、temperature、max_tokens 等可见 kwargs，因此两种字符口径也明确不同。

## 官方 Tokenizer 调查

[DeepSeek Token usage](https://api-docs.deepseek.com/quick_start/token_usage/) 提供本地 tokenizer demo，并强调 API Usage；[官方 DeepSeek-V4.1-Flash 仓库](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/tree/main) 有模型/聊天模板资源。可固定官方仓库版本不等于证明第三方 coco 当前部署使用同一编码与模板。

[官方 GLM-5.3-Flash 仓库](https://huggingface.co/zai-org/GLM-5.3-Flash/tree/main) 与 [Z.ai Flash 文档](https://docs.z.ai/guides/vlm/glm-5.3-flash) 是 exact Flash 系列的依据，不能拿 GLM-5.3 非 Flash 或 GPT 编码冒充。官方产品窗口也不证明 coco2 网关窗口。此次未读取真实网关配置、未请求模型，部署 revision/template/隐藏封装映射不可确认，因此两者当前都只能标记本地估算，未下载权重或执行远程 tokenizer 代码。

未来接入精确本地计数需要同时固定 tokenizer 文件哈希、chat template、特殊 Token、工具封装、部署版本，并用独立授权的 Usage 对照验证；即使完成，本地精确编码仍不必然等于服务端计费。

单供应商 SDK max_retries=0，避免隐式重试绕过预算；观察 hook 对额外重试安全拒绝。HTTP 观察是 pre-transport attempts，可能包含网络前失败，不能当服务端接收证据。Trace 原 metrics/冻结评分格式保留，新增 runtime_accounting 属性供新报告使用。离线断言覆盖语言/Schema/参数/结果/预留/未知窗口/strict/no dispatch/回退更小窗口/原历史/旧语义/缺失 Usage。
