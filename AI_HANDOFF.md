# AI_HANDOFF

## 当前状态

codex/coding-cross-file-canary-v2，从 C01 Live c56a03813f9a0472d72d96e5bc3915ff667f0d60 独立工作树开发。C02 OFFLINE PASS / LIVE BLOCKED，真实模型/摘要/Judge0，未发生真人命令审批；旧 C01 10/12 及 Strict PASS/元数据失败/私有账本均保留，余额不转移。

## 实现与验证

仅新 scripts/coding_cross_file_canary_v2、专项测试和文档，生产 mybot/ 与依赖无改动。csvmini parser/report 双模块，Public8/Host18；真实 Seatbelt Bug 均失败、Reference均通过。Gate 每 Revision 完整双文件 before/after maps、真实 delta、累计 Native Journal/Receipt、原 HEAD/Index/protected bytes；最终两文件均必须实际合法改变，未知漂移/发布不确定 HALT，不 reset。

Mock正式运行路径和 headed Chrome 两条修复路径 verified Revision1/2，Public8/Host18、刷新无请求/工具重放、exit0/SDK/DB/Lease/端口及独立 Profile 自动清理。双 Profile Cookie/LocalStorage隔离通过。第三个断流浏览器负例保留 HALT、正常清理。全部审批为 SYNTHETIC_APPROVAL，不作 Live Strict PASS。

最终全量 check_phase + 补充实际 2205 去重/63新增，失败0、源码快照不变；compileall/JS/diff/凭证资产审计通过。单文件/Receipt/SHA/部分发布/时序/审批/预算/断流等负例通过。可选 Contract 合法/拒绝独立记录，旧 C01 具体非法字段和需求覆盖仍 UNKNOWN。上下文仍可能裁剪，非通用语义保证。

## 下一步与边界

完整报告 docs/reports/coding-cross-file-canary-v2/，学习专题 docs/phases/coding-cross-file-canary-v2.md。Implementation后创建Preregistration提交，再唯一 prepare/freeze/verify；Acceptance仅改文档并Push独立分支、核对远程及再次verify。不得改冻结源码/Fixture/评分、重做prepare/freeze、重跑旧Case或访问旧私库。未来仅新精确 GRANTED_18_REQUESTS，且每次命令仍需真实人通过原WebApproval，Live operator禁止代批。用户Chrome/8765/真实项目、main/Tag/ZIP/共享AppleDouble不触碰。
