# AI_HANDOFF

## 当前状态

独立分支codex/stream-diagnostic-canary，基线ba759de36418d67008e98c8c7ddf05566dc520e5。D01只做离线准备，LIVE_AUTHORIZATION NOT_GRANTED；唯一新批次~/.mybot-mini/uat/stream-diagnostic-canary-20261026/。真实模型0，旧R01 FAIL/HALT/Case running及其余7次不触碰、不继承。

## 实现与验证

新增scripts/stream_diagnostic_canary/：单次SQLite/HTTP预算、透明SDK结构诊断、新Web入口、MockTransport/Chrome演练、唯一prepare/freeze/verify。正式create_app→Runtime→AgentLoop→ProviderFailover→SDK不替换，生产源码/依赖/旧UAT脚本报告不改。失败HALT与自有服务关闭分离，不清HALT换PASS。正文仅原生私有事件库，诊断导出元数据/哈希，报告不提交私有数据库。

252项去重专项回归通过（新增33），compileall/JS语法/diff通过。双profile Cookie/LocalStorage双向隔离通过；独立headed Chrome正常流与重复终态合成验证，两次打开SSE时exit0，端口/Lease/库一致。合成不证明真实DeepSeek兼容；旧问题原因仍UNKNOWN。完整报告docs/reports/stream-diagnostic-canary/。

## 下一步与禁止重复

唯一prepare/freeze已完成，冻结源码SHA c87a26b3532a640b4c604b5870c5bf638c095960；verify通过，真实请求/Attempt/reservation/HTTP均0。Acceptance只更新文档与证据。不要重复prepare/freeze、不要重建新账本。未收到新的GRANTED_1_REQUEST不得启动Live入口。授权后先verify，再查端口/Lease/进程/独立Chrome/库；新Session DOM发送唯一冻结消息一次，无重试/补跑/Steer。关闭只处理自有服务并实际wait exit0。原8765 launcher/用户Chrome不操作；不合main、不改历史Tag/ZIP。
