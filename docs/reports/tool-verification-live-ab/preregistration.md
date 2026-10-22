# 新样本真实 A/B 预注册（2026-10-22）

用户明确授权执行，并选择总128次物理请求、接受费用未知。仅此轮4个新任务×两组，共8个唯一Attempt，每个逻辑/物理上限均16；不是旧13例补跑，不进入Phase26。失败不补跑，剩余预算不用于新Attempt。默认不强制注入故障；保留既有自然failover策略。

Baseline源码：871510f8a682990da63448ef27ec282c376a8711。Candidate源码：04b6968fdab288d8562447e25c84a6d5cec3df41。两组在独立干净APFS detached worktree，由共享实验驱动分别启动全新Python进程；不改动或monkeypatch两个冻结Harness。共享驱动只提供相同新Benchmark对象、原已支持的request_audit、身份与公开预算；不追加测试入口提示，因此Candidate独有的生产提示保持为真实处理差异。

两个源码共享原有coding_judge与依赖锁的相同哈希。Judge必须执行在各原Harness内，评分调用原strict_success；共享新任务的fixture/public/hidden/reference全部在Live前冻结，两组相同。新私有测试由本轮设计者在冻结后续模型运行前编写，未给工具优化训练使用，也不会给被测模型访问；这不构成对设计者盲测的独立第三方样本。禁止Live后修改任务、参考、测试、Harness或评分来适配结果。

| 次序 | 任务 | 先运行 | 后运行 |
| --- | --- | --- | --- |
| 1 | bucket-boundaries-v1（easy） | Baseline | Candidate |
| 2 | quoted-cells-v1（medium） | Candidate | Baseline |
| 3 | reservation-flow-v1（hard） | Baseline | Candidate |
| 4 | span-coverage-v1（hard） | Candidate | Baseline |

每例公开2项、私有6项；全部输入规则写在公开任务中。原Judge验证缺陷版私有失败、参考版公开/私有通过。不给模型隐藏失败反馈，不运行结果驱动迭代。

固定配置：coco / deepseek-v4.1-flash，备用coco2 / glm-5.3-flash；主备配置字节相同并以哈希核对，不打印凭证或端点。模型标签是供应商别名，未提供可核验不可变后端版本或system fingerprint，因此不能宣称已证明服务后端版本一致。temperature=0.1、SDK retries=0、输出2048、单请求90秒、任务480秒、单Attempt总600秒；原工具48、Write3、命令6、无进展3、命令30秒限制保留。Context、Journal、Seatbelt、合法结束等均由原Harness配置决定，两组相同。

物理请求发送前：检查共享驱动/两组源码/新任务/配置冻结、Campaign及Attempt身份、全局128和每Attempt16的余量；先持久化reservation，再调用原SDK；结果持久化并与原provider_execution/terminal/raw交叉审计。HTTP至多等于物理尝试，不允许客户端自动重试造成漏计。旧Attempt目录、新目录已存在、上个Attempt不完整、全局stopped或ledger不完整均拒绝执行。

安全停止：Journal/Index/保护文件/工具ID/审批/Seatbelt异常、执行不确定、取消/中断、超时、Provider错误或Judge基础设施异常停止整个实验。确定的模型任务失败、预算耗尽、合法但Hidden Fail继续保留原失败并进入下一预注册槽；不改变Strict。每次原TTY审核须读取完整argv/cwd/副作用，再由Codex向真实PTY输入当次精确yes nonce，不自动循环批准。

主指标：原Strict（所有4个计划任务为每组分母）；辅助为Controller verified、公开/隐藏、Patch参数错误、stale、runner/Revision证据、逻辑/物理/HTTP、工具/Token、停止原因和安全清理。分类统一使用coding-failure-v2做派生解释，同时保留原failure；不改变Baseline原raw。没有可靠单模型价格时费用null，不能把未知当免费。

4对小样本只报告本轮观察及逐对结果，不据此推断总体成功率、生产稳定性或GLM自然恢复能力。若安全停止，剩余槽标为未运行/阻断并保留计划分母，不自行继续。

指纹说明：原report.grading_code_sha256对coding_judge、coding_fixtures、coding_benchmark、coding_live、coding_metrics共同封印；其中benchmark/metrics正是本轮A/B的生产改动，因此两组完整封印值应不同。预检另外逐字节核对真正Judge、fixture加载、live预算和coding_campaign.Strict规则文件一致；不能把完整封印差异误判成更改私有断言或评分标准。
