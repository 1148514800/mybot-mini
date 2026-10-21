# Provider Failover Harness Integration

这是Phase25之后的独立可靠性改进，不是Phase26。旧Phase25 Campaign、manifest v3、评分和模型结果不改变。

## 入口与隔离

```bash
# 默认single、默认离线；每次创建独立目录，不重放任何已开始Attempt。
uv run python -m scripts.evaluate_coding_failover
uv run python -m scripts.evaluate_coding_failover --provider-mode failover
# 上一次命令输出directory；用其实际路径查询，不重新运行。
uv run python -m scripts.evaluate_coding_failover --status --directory runs/coding_failover/<actual-directory>
```

新入口只在当前项目的runs/coding_failover下写入。每个v4 manifest只有一个Case/Attempt，默认cache-ttl-001，
可用--case-id选择已有Benchmark案例。没有恢复执行或重试命令；目录存在就拒绝重新运行，包含尚无finished的目录。
默认离线客户端只返回完成声明，故会形成可信的失败/blocked证据；这不是实际模型能力或严格成功。
完整修复路径由专项的合成DemoClient通过原Loop、Patch、Seatbelt真实测试、Journal和Judge验证。
底层evaluate API支持多Case及Repeat，每个Attempt重建主备状态，所有Attempt共享全局物理请求预算。

Live代码路径需要另外授权、有效的独立配置、真实stdin/stdout TTY、Seatbelt、两个费用标志及干净源码；
本阶段没有执行Live，禁止沿用此前剩余请求额度。旧evaluate_real_coding与evaluate_coding_campaign默认行为不变。

## 架构与计数

新coding_failover.evaluate的single分支直接调用原coding_benchmark.evaluate，不读取或创建备用配置/客户端。
failover分支仅在原run_task适配点安装FailoverCodingClient，复用ProviderFailoverClient，原AgentLoop仍决定工具操作。
每个Attempt新建主客户端，备用延迟创建；同Attempt内Sticky，结束后有界关闭两个客户端，再生成终态及Judge结果。

TracedClient的影子计数只计算逻辑轮次，不再修改全局物理计数。每次SDK create前同时受Attempt、请求/任务截止时间、
RequestBudget和Controller门约束；主请求由原Loop预占Controller，备用由before_fallback预占，不能补记或重复计数。
每任务Controller上限还受剩余全局预算约束，避免全局耗尽后原Loop额外预占一个主请求。

physical_model_requests统计SDK接口调用尝试，离线内存客户端只是合成接口计数；每条记录有client_kind和execution_mode。
http_model_requests仅在所有实际客户端均可观察HTTP发送钩子时给出，其他情况为null。
HTTP钩子是传输前发送尝试，MockTransport不是外部网络，发送尝试也不是供应商计费确认。

failover模式的llm_requests与Controller模型请求数按物理尝试计；logical_model_requests独立保留。
physical_requests_by_provider区分coco和coco2。fallback_attempts/successes/failures只统计真正发生切换的那次备用请求，
不把Sticky后续备用调用重复算为新的切换。预算或时限拒绝会保存在stops，不计为已发送备用请求。

## 策略、时限与隐私

Harness只对网络连接、请求超时、429、500/502/503/504回退。400/401/403及其他不可恢复HTTP状态、
协议不兼容、本地异常和取消不回退；SDK包装的明确本地异常和传输契约错误也不作为网络恢复。
生产CLI仍保留之前已验收的策略，新增严格谓词是可选参数，缺省不改变CLI。

原Loop的请求/任务总时限继续有效。主请求占用原时限的一半，备用仅使用同一逻辑请求剩余时间；
不能因为回退重置截止时间。SDK隐式重试均关闭，HTTP钩子拒绝同一个SDK调用出现意外重发。

记录Case/Attempt、逻辑/物理序号、Provider/Model、切换标记、阶段/状态、白名单错误类别/HTTP状态、
耗时和Usage；不存原异常、Key、Authorization、回复正文、Prompt、源码和工具参数。
缺失Usage和未观察到的HTTP次数为null，不用0冒充；混合模型没有可靠逐模型价格时费用为null，不能复用单模型价格表。

## 证据与验证

v4 manifest冻结主备标签、策略、实际预算和Agent配置、源码Git SHA及Python源码树哈希、依赖/Benchmark/评分/Schema、
费用模式、Case和唯一Attempt。冻结过程不沿用旧Phase25的默认时限；不存原始凭证或端点，仅保留必要的文件/端点哈希。
started/terminal/raw/finished/blocked均绑定身份。finished核对原始与terminal SHA、冻结来源、请求实际模型和Case；
失败、中断、不确定清理和证据缺失都不可重放、不可记为严格成功。离线运行不算Live strict_success。

```bash
uv run python -m scripts.check_coding_failover
uv run python -m scripts.check_provider_failover
uv run python -m scripts.check_provider_failover_smoke
uv run python -m scripts.check_coding_reliability
uv run python -m scripts.check_phase
uv run python -m compileall -q mybot scripts
git diff --check
```

最终结果和限制见[验收报告](reports/provider-failover-harness/acceptance-report.md)。
