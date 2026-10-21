# Provider Failover Harness Integration 验收报告

结论：**OFFLINE PASS**。新增50项专项、最终1071项/29套件全部通过；真实模型API请求为0。
本阶段是Phase25之后的独立可靠性改进，不是Phase26，不是Live验收，也不代表编码任务成功率提高。

## Git与执行版本

- 已fetch并核对远程验收基线：`5490149827cffbc5c75aa6cc1634efeb33344c0a`，没有更新差异。
- 独立分支：`codex/provider-failover-harness`。
- 工作区：`/Users/godblack/.codex/worktrees/provider-failover-harness/mybot-mini`。
- 集成实现提交：`f90434ba7781d147793c995b52120c16cb2111c5`。
- **最终实现SHA：`9bf58ba90d5391cb4782a342c94a2ef5b46e17ba`**，包含离线模型标签隐私修复。
- 最终回归在集成提交加该隐私修复的工作树上执行；提交没有改变被测Python源码。提交后的完整合成证据再次运行，记录上述最终实现SHA及源码树SHA。
- 本报告和脱敏证据另作本地文档提交，交付提交SHA在最终回复及Git日志中提供。不Push、Merge或移动历史Tag。
- 环境：macOS 26.6.2 arm64、Python 3.12.14、uv 0.12.10；使用`uv sync --frozen --offline`安装锁定依赖。
- 本轮未复制或修改真实配置/Key。离线使用内存桩或真实SDK的MockTransport，不使用上一轮剩余额度。

## 架构与修改文件

| 文件 | 实现 |
|---|---|
| `mybot/provider_failover.py` | 现有切换器增加可选recoverable谓词，缺省保持原CLI策略 |
| `mybot/evaluation/coding_failover.py` | 严格策略、原逻辑Trace适配、物理前预算、逐Provider元数据、Usage/HTTP未知值、成本隔离 |
| `mybot/evaluation/coding_benchmark.py` | 仅显式适配模式安装客户端、绑定原Controller、限制全局剩余预算、逐Attempt有界关闭及终态留证 |
| `mybot/evaluation/coding_live.py` | 复用原TTY/费用/Seatbelt门但按Attempt创建SDK；保留预算拒绝异常供原Loop安全结束 |
| `mybot/evaluation/coding_failover_campaign.py` | create-once v4 manifest、冻结真实运行配置与源码、身份/哈希/来源/请求模型校验 |
| `scripts/evaluate_coding_failover.py` | 默认single/offline的独立入口，证据限于当前项目runs/coding_failover |
| `scripts/check_coding_failover.py` | 50项专项，包括真实SDK MockTransport和原Agent全流程 |
| `scripts/check_phase.py` | 追加新套件，保留原1021项 |
| README、`docs/provider-failover-harness.md`、AI_HANDOFF及本目录 | 架构、运行、限制和交接证据 |

本轮不改AgentLoop、Controller、Patch、run_command、审批、Seatbelt、Judge、Fixture、Gold和隐藏测试。
旧evaluate_real_coding、evaluate_coding_campaign入口保留。single分支直接调用原evaluate，不解析或创建备用客户端，旧报表字段无新增混合字段。

## 计数与预算

调用链为原配置/Loop/Controller/Session加显式FailoverCodingClient适配器，切换机制仍是同一个ProviderFailoverClient。
TracedClient改用局部影子计数计算逻辑请求；共享RequestBudget仅在物理SDK接口调用前增加。
原Loop预占主请求Controller预算；before_fallback先检查Attempt、时限和全局预算，再预占备用Controller预算。
Case的Controller请求上限还取剩余全局预算的较小值，避免全局耗尽后额外预占主请求。

记录logical_model_requests、physical_model_requests、physical_requests_by_provider、fallback_attempts/successes/failures。
最后三项只统计实际切换的第一条备用请求，不把Sticky后续请求重复算作切换。预算拒绝保留stops，不计为已发备用请求。
新模式llm_requests按物理尝试计；原模式语义不变。successful_responses/api_failures保留逻辑请求最终结果语义；已恢复的主失败仍完整留在逐物理记录，不可用legacy api_failures冒充物理错误总数。Controller/schema预占和逻辑Trace各有自身用途，不重复扣全局请求。

SDK接口尝试与HTTP发送分开。每条记录标明offline_synthetic/live及synthetic_client/openai_sdk。
HTTP钩子只能证明发送前传输尝试；MockTransport不是外部网络，不能冒充真实API；无HTTP观察时为null。
SDK禁隐式重试，意外重发/错误端点由传输门拒绝，不能把SDK包装的本地或契约错误当作网络回退。

## 生命周期、错误与时限

每个独立Case/Attempt新建主状态并从coco开始；备用延迟创建，同Attempt内Sticky；下一Attempt重新从主模型开始。
网络、超时、429、500/502/503/504可回退；400/401/403、其他不可恢复HTTP状态、协议不兼容、本地异常及取消不回退。
主请求失败只有在策略、全局预算、Controller和截止时间全部允许时才进入备用；不重放Agent、工具批次、Patch或命令。
备用自己的模型和Key独立使用，消息与Schema保持相同。

原请求/任务/总截止时间继续有效，主请求预留原时限的一半，备用仅使用同一逻辑请求剩余时间。
取消或撤销后不再启动备用；迟到响应不更新成功状态。逐Attempt关闭通过既有5秒有界清理屏障，异常或未确认清理标记execution_uncertain并保留证据/Workspace。

## v4证据与单模型隔离

新目录只使用runs/coding_failover。每个manifest一个Case/Attempt，冻结主备模型、策略、实际时限/预算/Agent配置、
Harness SHA及Python源码树SHA、uv.lock、Benchmark、Grading、工具Schema、Case/Attempt和费用模式。
不保存原始Key或端点；必要配置与端点仅保留哈希。冻结实际配置，不沿用旧Phase25的90/600秒默认值。

manifest v4且kind=provider_failover_harness，与旧v3明确分开。started/terminal/raw/finished/blocked绑定相同身份。
finished校验raw/terminal SHA、冻结来源、Case及实际请求的Provider/Model；即使重算文件哈希，错误来源或模型仍会被拒绝。
目录存在就拒绝再次执行，没有恢复或自动重放命令；失败、中断、清理不确定和证据不完整都不可记为严格成功。
离线严格成功为false；原single API/报表及旧Campaign既未覆盖也未混算。

## 实际测试结果

| 执行命令 | 通过/总数 | 结果 |
|---|---:|---|
| `uv run python -m scripts.check_coding_failover` | 50/50 | PASS |
| `uv run python -m scripts.check_provider_failover` | 17/17 | PASS |
| `uv run python -m scripts.check_provider_failover_smoke` | 13/13 | PASS |
| `uv run python -m scripts.check_coding_reliability` | 42/42 | PASS |
| `uv run python -m scripts.check_phase` | **1071/1071，29套件，跳过0** | PASS |
| `uv run python -m compileall -q mybot scripts` | 退出0 | PASS |
| `git diff --check` | 退出0 | PASS |

专项亦在全量中执行，不重复相加作为独立覆盖数。原1021项保留，Phase1/2兼容断言通过。
初次1070项回归也通过；其统计保存在offline-validation.json。隐私修复后50项及最终1071项重新执行，见offline-validation-final.json，不改写前次结果。

| 关键故障注入/反例 | 实际结果 |
|---|---|
| single、主请求成功 | 不创建备用；single报表无混合字段 |
| APIConnectionError、APITimeoutError、429、500/502/503/504 | 回退成功，1逻辑=2物理，Controller与全局均计2 |
| 400/401/403/422/501 | 不回退，保留类别和允许的HTTP状态 |
| 工具协议重复ID、备用协议错误 | 不掩盖；不记恢复成功或任务成功 |
| 本地异常、SDK包装的明确本地异常、重定向/重发契约错误 | 不作为网络回退，实际HTTP不超限 |
| 主备真实SDK MockTransport | 各用自己Key/模型、相同消息/Schema；主503后仅备用1次，禁SDK重试 |
| 全局或Controller仅剩1次 | 主请求后停止，备用SDK/客户端不启动，无虚假verified |
| Sticky、新Attempt/多Case | 同Attempt只切换一次；下一Attempt从主开始且身份不同 |
| 取消前/等待中/迟到响应、任务/总时限 | 不启动后续备用，不接收失效成功 |
| 备用失败、双客户端异常关闭 | 不无限重试；两端关闭均尝试，失败留execution_uncertain/blocked |
| 错误/Key/正文/Prompt | 不进入元数据；缺Usage和HTTP观察保持null |
| Patch未测试、旧修订要求 | 不verified，沿用原Controller/Judge标准 |
| 完成读取后再发生模型失败 | 读取不重放，Session工具ID完整配对 |
| v3拒绝、完成/started再执行、SHA/身份/冻结来源/模型篡改 | 拒绝重放或拒绝证据；不写旧Campaign |
| 取消中的独立Campaign | 保留started、terminal和blocked，无finished，不重放 |
| 模型字段误填离线备用Key | 合成复现后修复；清除凭证前以全部已知Key检查标签 |

## 完整合成任务与入口实跑

最终实现提交上的synthetic-verification-final.json记录：

- 原AgentLoop因主连接异常恢复到备用，5次逻辑请求、6次合成物理接口尝试，Controller计6。
- Provider分布主1、备用5；fallback_attempts=1、successes=1、failures=0。
- 原生Patch提交1、真实Seatbelt unittest运行1、Revision=last_verified_revision=1。
- Agent verified、工作流成功、Judge hidden_pass；工具ID配对、Journal归属、Index与受保护/无关文件检查通过。
- 两个客户端各关闭1次，清理确认；HTTP次数及Usage未知为null。
- 全部是离线模型桩，因此strict_live_success=false，v4状态保守保留blocked，不冒充真实编码任务完成。

原实现提交的对应证据synthetic-verification.json也保留，未覆盖。single/failover两个CLI入口均实际离线执行，
最终入口状态分别见entry-single-final.json和entry-failover-final.json。默认客户端仅声明完成，实际均blocked且strict_success=false，证明没有把文本恢复当任务成功。

## 审批、隐私与保护

需要Codex代答的CLI/平台审批提示0次，Codex实际yes输入0次；没有关闭、缓存或绕过审批。
既有42项生命周期专项中的真实PTY合成用例自动测试当次nonce批准、裸yes/旧nonce拒绝和取消读入，不冒称为本轮真实模型审批。

本轮真实模型API请求**0**，未使用上轮剩余1次额度，没有Live Benchmark或外部项目模型调用。
混合费用字段仍为null：未实现可靠的逐模型价格配置时拒绝沿用单模型价格或成本上限，不能伪造估算。
所有模型元数据只有Case/Attempt/序号、标签、阶段/状态、类别/HTTP码、耗时、Usage和停止信息；不存Key、Authorization、回复正文、完整Prompt、源码或工具参数。

1592项保护文件SHA复核不变，覆盖原Phase25冻结工作区/Campaign、此前验收区、主工作区用户修改和检查到的归档。
main和历史Tag引用保持，无ZIP重导出，无已完成Slot或旧API报告重写。真实Key未复制到本工作区，提交扫描不包含Key或真实配置。
原Git共享对象目录的AppleDouble pack索引错误未清理；必要读取、完整回归与保护检查成功，未借此执行reset/clean或改写历史。

## 限制与后续

最终结论仅为**OFFLINE PASS**。实际新Harness的主备连接、真实任务能力、真实取消/供应商故障分布、混合成本及长期稳定性均未做Live验收。
本轮只支持独立create-once Campaign目录；不提供续跑、自动重试或旧v3迁移。已完成/失败Attempt不能自动重放。

具备另行授权后启动独立Live Coding Benchmark的工程条件：应在干净新版本上配置凭证、冻结混合模型/策略/预算、逐物理请求验收。
不得直接继续旧Phase25 DeepSeek Campaign，不混入Astra或旧单模型分母，不因合成任务成功宣称模型成功率提升。
