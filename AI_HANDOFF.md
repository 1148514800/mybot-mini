# AI_HANDOFF

## 当前状态

新样本真实A/B已完成：分支codex/tool-verification-live-ab，实验/预注册冻结553de2d39d0ddab8e54cce79ba69af1db83dfb58。用户授权128次总物理请求、接受费用未知；实际8个预注册唯一Attempt、60逻辑/物理/真实HTTP，剩余68不用作新Attempt。OFFLINE PASS / LIVE INFRA PASS；不是Phase26，不合并main，不动历史Tag/ZIP。

## 结果与证据

Baseline 871510f8a682990da63448ef27ec282c376a8711 与 Candidate 04b6968fdab288d8562447e25c84a6d5cec3df41 均Strict3/4、Controller verified3/4、Hidden Pass3/4；Candidate一赢一输两平，未证明总体成功率提升。Baseline32请求/43工具/144062Token，Candidate28/43/137350；4次请求差中3次来自Candidate提前失败，不当同质量效率收益。合计281412可观察Token、Usage完整，费用unknown/null。

Candidate bucket成功Preview后下一Patch在argument_parsing invalid_arguments停机，意图及字段unknown；Baseline reservation可恢复Preview错误后正式Write validation invalid_arguments停机。两者未提交、不补跑。Baseline quoted一次stale Preview后模型显式恢复；Candidate span第一次Patch前测试无当前证据、Patch后测试才验证Revision1。实时错误不触发自动重放或放宽门。

全部60次为coco DeepSeek，GLM0/natural fallback0；没有强制故障、取消或超时。真实PTY审核8次（7次unittest+1次只读公开模块哈希），拒绝0、nonce复用0。所有工具ID、Journal/Index/保护文件、清理/安全审计通过；154份脱敏证据与SHA清单，入口docs/reports/tool-verification-live-ab/acceptance-report.md，原Campaign位于runs/tool_verification_ab/campaign-v1，只读保留，禁止重放。

## 实现与验证

共享scripts/tool_verification_live_ab.py只编排原Harness，两个冻结源码在独立干净APFS进程运行，不monkeypatch、不改生产代码/审批/评分。4个新自包含任务，每例公开2/私有6，Live前固定，模型不见私有断言。每Attempt16逻辑/物理、输出2048、90/480/600秒，其余原工具/Write/命令/无进展限制保留。全局128先持久预留再SDK，并交叉核对terminal/raw/HTTP。Model标签固定但不可核验供应商不可变后端版本。

新增29/29；全量1187/1187、33套件零跳过，原1158保留；编译/diff通过。两组真实Judge/fixture/live/Strict算法文件一致，整体grading封印因被比较的benchmark/metrics文件不同而不同。实验后只增报告/交接，无源码或任务调参。

583项旧保护文件、旧13例/Canary/Phase25/前轮闭环报告、main、26个Tag、53个ZIP及原配置保持；临时0600配置副本结束后校验移除，凭证不提交。前轮闭环入口docs/reports/tool-verification-reliability/保持只读。

## 下一步与边界

本轮授权已按全部预注册槽完成，不用剩余额度补跑，不再发Live。没有真实成功率/成本提升证据；4对新构造任务非生产自然样本，作者并非盲测，不能把它们再称未见。可另行离线研究有限解析诊断，保持Write和未知意图停机；不猜历史非法字段、不基于私有答案调参。任何新Live需新授权、样本和冻结，不自动进入Phase26。GLM、自然回退、长期取消、失败测试修复和edited_unverified归因没有新增充分Live证据。
