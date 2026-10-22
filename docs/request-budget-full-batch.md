# 请求预算与完整Coding Batch

这是Phase25之后的独立工程实验，不是Phase26。旧Canary表明：修复与unittest/隐藏测试通过不保证Agent已正常收尾，额外检查可能耗尽最后一次请求。旧结果不改判。

## 最小策略修改

CodingTaskController.instruction只新增元数据提示，不改状态机、预算、工具或Judge。can_verify真实成立时要求优先最终回复；最后一次请求要求根据真实证据决定必要操作或如实报告未完成。不会自动回复或把can_verify转换为verified。仍要求原生Patch、真实批准测试、当前Revision与文件哈希一致。减少重复规划说明，保留跨模块调用链、Patch参数/恢复、审批、沙箱及测试限制。不要用synthetic对照推断真实能力改进。

## Batch与逐请求账本

scripts.run_coding_failover_batch顺序调用现有v4.run，一目录13个固定槽位。自然12例按Easy12/Medium16/Hard20次上限，共192；独立受控cache-ttl例12次；全局204。每例独立480秒任务/600秒整体、90秒请求，2048输出，SDK隐式重试0。

batch.json原子持久保存固定计划、所有实际v4冻结信息和预算。每槽先写启动意图，再由v4创建唯一身份。每次SDK接口尝试之前，RequestLedger核对计划、冻结源码/配置、全局及单例余额，原子写请求reservation；调用结束写独立outcome。自然失败可以继续，但生命周期/证据/清理/权限异常立即停止。连续两个自然Case发生Provider故障也停止，避免持续故障消耗。现有目录始终拒绝执行，没有resume或自动重试。崩溃时未完成启动意图或请求reservation保留为审计阻断，不能推断未发送而补跑。

JSON使用同目录临时文件fsync后no-clobber hardlink发布，再fsync目录；不覆盖已存在证据。只读status交叉检查v4身份/SHA、请求reservation/outcome与最终报告、唯一Attempt、固定预算、槽位receipt。哈希检测意外损坏，不声称抵抗有能力同时重写全部证据的攻击者。

## 独立受控故障

fault_mode=primary_connection_once只在独立受控槽冻结启用；自然模式仍none，原CLI不启用它。首次主模型SDK接口边界记录一次本地APIConnectionError，不调用主SDK HTTP方法：物理接口尝试1、Controller预算1、全局预算1、HTTP0、synthetic_injected=true。由现有回退机制预占备用物理预算，使用备用自己的Key/Model，并在同Attempt sticky。后续不再注入、不轮询、不重放工具。12次受控上限包括这1次合成尝试，最多11次真实备用请求。自然/受控统计分开。

离线真实OpenAI SDK+MockTransport已验证主HTTP0、备用独立认证与模型、同Attempt sticky、3物理/2HTTP/3Controller计数；另一路通过原AgentLoop、Patch、Seatbelt公开测试与Judge。不是自然故障或真实模型能力证据。

## 命令

```bash
uv run python -m scripts.check_request_budget_efficiency
uv run python -m scripts.check_coding_failover_batch
uv run python -m scripts.check_coding_failover
uv run python -m scripts.check_coding_reliability
uv run python -m scripts.check_provider_failover
uv run python -m scripts.check_provider_failover_smoke
uv run python -m scripts.check_phase
uv run python -m compileall -q mybot scripts
git diff --check
# 所有离线通过且implementation已提交、源码干净后，仅在明确费用授权下：
uv run python -m scripts.run_coding_failover_batch --live --confirm-api-cost \
  --suite full12-plus-forced --max-physical-requests 204
# 仅查询，不恢复执行：
uv run python -m scripts.run_coding_failover_batch --status \
  --directory runs/coding_failover/full-batch-001
```

真实命令逐次TTY/nonce审批，不能yes管道或缓存授权。报告不存凭证、Prompt、回复正文、原始Patch、命令敏感正文或nonce。缺失Usage/HTTP为null；费用unknown，不是免费。CLI退出0不代表TASK PASS，v4 blocked也不自动等于执行不确定。

## 验证与交付

新增18项效率专项、25项Batch专项接入全量；原1071项不删不弱化。合成前后对照在相同5次预算下，脚本旧策略额外读取导致budget_exhausted，新提示使脚本正常收尾；这只是响应规则的synthetic验证，不是真实模型对照试验。最终真实结果与局限以docs/reports/request-budget-full-batch为准，implementation与acceptance分别提交，不改历史Tag/ZIP。
