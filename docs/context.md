# Context 与资源计量

旧配置保持兼容：`max_chars` 永远是 JSON 字符预算，默认 `legacy_chars` + `deterministic`。它不能保证模型 Token 窗口。原 SessionStore 格式与历史保留轮数没有迁移。

建议在现有配置中合并以下 `context`；API Key 继续只放本地配置。CLI/Web 均需重启生效。

```json
{
  "context": {
    "enabled": true,
    "max_chars": 40000,
    "recent_turns": 2,
    "summary_max_chars": 3000,
    "tool_result_max_chars": 4000,
    "token_budget": {
      "mode": "estimate",
      "input_limit": 48000,
      "model_windows": {}
    },
    "compaction": {
      "mode": "deterministic",
      "allow_extra_requests": false,
      "max_calls": 1,
      "input_tokens": 12000,
      "output_tokens": 1200,
      "timeout_seconds": 15,
      "on_failure": "deterministic"
    }
  }
}
```

`estimate` 在发送前限制完整可见请求的保守估算值；不是精确 Token 保证。当前没有已验证的网关 Tokenizer 映射，`local_tokenizer_tokens=null`。`strict` 会拒绝所有未验证请求，包括手工填了窗口的模型；不要把它当作可立即启用的精确计数模式。

只有获得实际网关部署证据后，才在 `model_windows` 添加 `provider/model` 对应的整数窗口，例如自己的 coco 与 coco2 模型分别配置；不要直接抄官方产品窗口。实际输入上限为 `min(input_limit, window-max_completion_tokens)`。窗口缺省时显示 unknown，使用显式 input_limit；没有精确剩余 Token。备用模型发送前重新检查自己的模型键及输出预留。

计量使用完整可见 request 的 JSON 字符数、UTF-8 字节数；估算为 UTF-8 字节数 + 256 + 每消息32 + 每工具64 的封装余量。这是对普通文本偏保守的启发式，未知服务端隐藏提示和编码可能超出余量，不能保证供应商接受或精确计费。工具 Schema、参数、结果、System、Skills、Plan、摘要都计入。中文与 Emoji 的字节数和估算通常高于同字符数英文。

启用语义摘要：将 `compaction.mode` 改为 `semantic`，同时设置 `allow_extra_requests=true`。当旧完整轮次被移出请求视图时，最多发起 max_calls 次摘要机会；每次可能产生一个主模型请求和一次有条件回退，因此潜在物理请求最多为两倍。摘要也消耗 Controller/Evaluation 预算和 Usage，费用未知；本轮只用合成模型验收，生产启用会产生真实费用。输入同时受 compaction.input_tokens 与当前主请求输入上限约束，输出通过 max_tokens 和响应字节上限约束。

摘要是九字段、带来源轮次/消息/角色的原文引用选择，不允许自由编造事实。每来源最多保留1024字符左右的有标记节选；模型最多选择每字段6条、每条500字符。历史内容仍可能被错误分类或遗漏，必须重新读取当前文件并验证。摘要以 assistant 低信任参考出现，不能恢复 Receipt、审批、Plan 完成状态、Revision 或测试证据。当前 System、用户输入、工具配对和 Skills 不做语义压缩。

格式不合规、超时、输入超限等默认回退规则摘录；`on_failure=stop` 则安全停止。调用额度用完时使用规则视图，不新增请求。取消会传播。摘要只在本次 handle_message 中缓存，按完整历史/脱敏集合哈希失效，不写入 Session、磁盘或长期记忆。原 Session 仍遵循原 max_turns 容量规则。

CLI 的 `[RESOURCES]` 和 `[CONTEXT]`、Web 活动面板，以及 Trace.runtime_accounting 使用同一份每轮快照。logical_requests 是逻辑调用；physical_requests 是底层客户端调用，包含失败/备用模型/摘要；HTTP 是 SDK transport 前观察到的发送尝试，不能等于计费成功。合成 Client 无可观察 transport 时 HTTP=null。Usage 缺失总量为 null，另有已知 subtotal；既不补零，也不用估算反推费用。对照摘要轮次编号时，以本次保留的 Session 轮次为准。

CLI 与 Web 对同一路径使用合作式进程锁。CLI 从启动至退出持锁（包括等待输入），Web 每任务持锁至 MCP/客户端/执行清理结束。不确定清理保留锁至进程退出；不会删除旧锁文件。不同工作区可独立运行。此锁不协调外部编辑器、不合作的嵌入 Agent 或不同工作区共用的 Session 路径，也不是恶意同 UID 进程的安全隔离。

验证：`uv run python -m scripts.check_token_budget`、`uv run python -m scripts.check_context_compaction`、`uv run python -m scripts.check_runtime_accounting`。完整审计见 [验收报告](reports/project-debt-modernization/acceptance-report.md)。
