# Provider Failover 完整验收报告

结论：**PASS**。离线验证 PASS，真实 API 测试 A/B 均 PASS；本轮真实 HTTP 模型请求尝试 **3/4**，未重复 Live，剩余额度不使用。此结论仅适用于本次连接与故障切换验收，不代表编码任务成功率或长期可靠性提高。

## 版本与环境

- 验收分支：`codex/provider-failover-acceptance`。
- 从远程 `origin/codex/provider-failover-smoke` 获取的实际基线：`ef92f34df509a091ff16eeceab01b746eebe7760`，包含原实现 `d07f64d`。
- 执行测试及 Live 时 HEAD 为上述基线，包含本报告列明的未提交修复；两次 Live 的实际脚本 SHA256 均记录于 started JSON。最终本地验收提交见交付 Git SHA；不以基线 SHA 冒称修复后已提交版本。
- 独立目录：`/Users/godblack/.codex/worktrees/provider-failover-acceptance/mybot-mini`。
- macOS 26.6.2 arm64、Python 3.12.14、uv 0.12.10；`uv sync --frozen --offline` 成功安装37个锁定依赖。
- 从已有 provider-failover 工作区复制忽略的配置，权限0600。主备用均有凭证，端点均匹配 `https://www.sub-coco.org/v1`；不打印或提交 Key。
- 主模型 `coco/deepseek-v4.1-flash`，备用 `coco2/glm-5.3-flash`；原配置和副本内容没有被测试写回。

## 离线实际执行

| 命令 | 通过/总数 | 结果 |
|---|---:|---|
| `uv run python -m scripts.check_provider_failover` | 17/17 | PASS |
| `uv run python -m scripts.check_provider_failover_smoke` | 13/13 | PASS |
| `uv run python -m scripts.smoke_provider_failover` | 17/17 | OFFLINE PASS，重复运行既有17项，不另计独立覆盖 |
| `uv run python -m scripts.check_phase` | 1021/1021，28套件 | PASS，含原991项/26套件、故障切换17项、smoke13项 |
| `uv run python -m compileall -q mybot scripts` | 退出0 | PASS |
| `git diff --check` | 退出0 | PASS |

Phase1/2兼容断言亦通过。初始未修复版本的17项故障切换、5项smoke和默认17项离线smoke也均通过；随后另行复现了原5项未覆盖的统计缺陷。完整运行结果计数与本地日志SHA见 `offline-validation.json`；没有删除断言或降低标准。

覆盖 APIConnectionError、APITimeoutError、APIStatusError、成功不切换、备用独立模型/凭证、Sticky、重新构造客户端恢复主模型、取消不回退、备用失败不重试、Controller请求预算与拒绝状态、工具不重放、Session工具ID配对、双客户端关闭、日志脱敏。

真实SDK的 MockTransport 测试使用合成Key检查 Authorization、模型和消息上下文，模拟主503后连续两次备用响应且关闭两端；没有访问真实模型。实际HTTP钩子的离线测试验证了计数和两次上限。已有审批、真实PTY、Seatbelt、Patch、Journal、Revision及Judge安全回归保留。

## 发现的问题与最小修复

1. **请求计数少报，已直接复现。** 原自然模式主请求失败后实际调用主备用各一次，但 `model_requests=1`，把应用层轮次当作物理请求。现在分别记录逻辑轮次、SDK调用和发送前HTTP钩子计数，强制模式的本地注入不计为付费请求。每个probe最多两次，SDK隐式重试仍为0。
2. **外围超时协调不足。** 原外围使用命令行与配置时限的较小值，主预留却使用原配置的一半；当外围更短时可能在备用开始时提前取消。现在仅复制probe配置，将较小时限同时用于外围与主预留；不写文件，不延长时限，不改变生产CLI策略。离线测试确认传给工厂的时限与外围一致。
3. **失败缺少可信统计。** 原CLI失败只打印异常类型，不能交付已发生请求数及清理证据。现在失败也返回白名单JSON，记录阶段、异常类型、可用HTTP状态、请求回执、耗时和关闭结果；不保留原异常字符串、响应正文或凭证。
4. 原smoke专项未接入全量入口。现加入 `check_phase`，保留原5项并增加8项针对性测试，总计13项。

本轮仅修改smoke脚本、其专项测试、全量测试入口及文档；生产 `mybot/provider_failover.py`、AgentLoop、Controller、工具、审批、Seatbelt和原单模型评测入口未修改。

## 真实API测试 A：强制故障切换

命令：`uv run python -m scripts.smoke_provider_failover --live --confirm-api-cost --mode forced --timeout-seconds 60`。

**PASS**，只执行一次，真实PTY会话10119，退出0。

- 本地注入主失败1次；主模型真实请求0次。
- 备用真实HTTP请求2次，均以 `glm-5.3-flash` 发起并返回有效非空文本；只保留文本长度2，不保留正文。
- 第二次请求仍使用coco2，注入器只调用一次，Sticky验证通过；最终active_provider=coco2。
- 请求耗时2.548213秒、1.949796秒；总耗时4.512549秒；输入Token34、输出6、合计40。
- 两个请求共用既有配置，SDK调用计数与HTTP发送计数均为0/2；清理确认。

证据：`live-forced-started.json`、`live-forced.json`。

## 真实API测试 B：自然路径

命令：`uv run python -m scripts.smoke_provider_failover --live --confirm-api-cost --mode natural --timeout-seconds 60`。

**PASS**，只执行一次，真实PTY会话93514，退出0。

- 主模型真实请求1次，以 `deepseek-v4.1-flash` 发起并返回有效非空文本；备用0次，最终active_provider=coco。
- 请求耗时2.505506秒；总耗时2.506073秒；输入Token9、输出1、合计10。
- 主模型正常，因此**没有发生自然故障切换**；不能将此测试写成自然故障恢复验证。
- B在A之后以全新进程启动，重新优先使用coco，支持程序重启后恢复主提供商初始选择；不代表反复重启或长期稳定性已验证。
- SDK调用与HTTP发送计数均为1/0，清理确认。

证据：`live-natural-started.json`、`live-natural.json`。

## 合计、审批与安全

- 共3次真实HTTP模型请求尝试：主1、备用2；两次probe各只运行一次，无自动重试、无第四次请求、无付费Benchmark或外部项目调用。
- HTTP钩子在发送前计数，并不是供应商计费确认；SDK隐式重试关闭。总输入43、输出7、Token50；价格表缺失，费用unknown/null，**不是免费**。
- 两个probe均为常量文本，不启动AgentLoop，不执行工具、命令或Patch，不发送仓库、用户文件或Session内容。
- 本轮操作没有出现CLI yes/nonce审批提示，Codex实际输入yes为0次；不伪造审批记录。真实PTY与nonce机制由原有离线合成回归覆盖，不冒称为本次Live审批验证。
- 调用链 `config → build_gateway_client → ProviderFailoverClient` 具备真实API证据；`AgentLoop → Controller → Session` 通过原Loop合成测试验证预算、工具不重放、ID配对及不能无真实Patch/测试而verified。不能把两类证据拼接成真实编码任务已成功。
- 凭证路由由实际SDK合成传输测试验证，真实备用请求有效返回；日志与提交前逐文件扫描均不含实际Key。
- 1115个保护文件SHA复核一致，覆盖原冻结工作区、Campaign、其他工作区用户文件与检查到的历史归档；main和历史Tag引用不变。原CSV blocked证据没有删除或修改。
- Git仍报告历史AppleDouble `._pack-*.idx` 的 non-monotonic index 错误；必要读取、测试及保护核验成功，本轮未修复或删除这些文件。

## 未验证与后续边界

自然API故障在本轮未出现；真实取消、真实备用故障/耗尽、跨进程长期稳定性、Coding Harness混合模型任务质量和成本均未进行额外Live验证。取消、备用错误、异常关闭及预算耗尽边界仅由离线合成用例支持；正常关闭与新进程恢复主提供商有本轮Live证据。没有平台强制审批BLOCKED，也没有Live FAIL。

**达到本次Provider Failover连接与安全验收标准：PASS。** 具备接入独立新版本Harness评测的工程条件，但需另行授权并冻结混合模型、计数及结果来源；不能自动继续旧Phase25单模型Campaign，不能声称编码成功率提高或长期稳定性已通过。

所有结果保存在本独立验收分支，创建本地提交；不Push、Merge、进入Phase26、移动Tag或重导出ZIP。
