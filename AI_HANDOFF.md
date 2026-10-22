# AI_HANDOFF

## 当前目标

执行新样本真实A/B：用户明确授权128次总物理请求，接受费用未知。分支codex/tool-verification-live-ab；不是Phase26，不合并main，不改旧Attempt/报告/Canary/Tag/ZIP。

## 冻结与架构

Baseline 871510f8a682990da63448ef27ec282c376a8711，Candidate 04b6968fdab288d8562447e25c84a6d5cec3df41，独立干净APFS worktree。共享scripts/tool_verification_live_ab.py只编排，分别使用原Harness的新进程，不monkeypatch、不改评分或审批。新4任务、每例公开2/私有6，设计与参考在Live前固定；旧13例不补跑。每组4例，同预算16逻辑/物理请求、输出2048、90/480/600秒；coco DeepSeek与coco2 GLM自然failover配置字节相同，未强制注入。配置别名固定，真实不可变后端版本未知。

新增29项检查接入check_phase；1187/1187（33套件）、专项29/29、编译/diff通过；冻结两组离线预检均验证4例有效、相同新任务与Judge/Strict算法。整体grading封印包含被比较的benchmark/metrics，因此两组该指纹不同属预期。

## 证据与执行边界

预注册/离线验证入口docs/reports/tool-verification-live-ab/。共享Campaign目录runs/tool_verification_ab/campaign-v1；每物理请求预留与结果持久记录、全局128/每Attempt16先检查后SDK。8个唯一槽按AB/BA交替；目录已存在、上个Attempt不完整或stopped均拒绝重放。安全/审批/清理/超时/Provider/评分基础设施异常停整个实验；确定任务失败保留分母并继续下一预注册槽。

每次真实PTY审核读取完整命令、cwd、效应再输入当次yes nonce；禁止批量/预输入yes。主备配置只复制到冻结worktree忽略的0600文件，不输出或提交密钥；实验源码及资产须提交并保持干净后才能Live。请求、报表、审批审计写入忽略的runs目录，Live期间不改源码/任务/测试/评分、不提交HEAD。结束后只新增脱敏证据/报告及交接提交，不更改冻结。

## 下一步

离线已通过，准备提交共享驱动/新样本并创建唯一Campaign；然后执行8个槽（本检查点真实HTTP0）。最终按原Strict报告全部计划分母、失败与预算、yes次数，核对历史保护哈希，Push独立分支。不把4对样本当总体能力提升。前轮闭环结果见docs/reports/tool-verification-reliability/，保持只读。
