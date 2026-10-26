# AI_HANDOFF

## 当前状态

Streaming & Steer真实Provider UAT离线准备，LIVE_AUTHORIZATION=NOT_GRANTED。分支codex/streaming-steer-live-uat，基线3a8a3d67d7305bb55a357b8a851dde0446fc2c4f。新增scripts/streaming_steer_uat及独立check_streaming_steer_uat；生产mybot/config/依赖与旧冻结资产不改。唯一新批次~/.mybot-mini/uat/streaming-steer-live-20261026已prepare、唯一freeze并verify通过，Preregistration 75e79d2ed7fd6c14beef326f025667c3f61085ba；真实请求/Attempt/reservation/HTTP均0。

## 实现与验证

复用旧持久SQLite预算门，但新上限R01/R02/R03/R04=1/4/1/2，总8；一Case一Attempt，不转移。新SDK代理保留reservation至流消费和关闭结束，首Chunk前后失败/取消均计数，HTTP钩子阻止隐藏重试。SDK原块原样转发，R02/R03/R04首个非终态Chunk后每物理流冻结8秒屏障，不作自然延迟。

UAT专用Registry工厂在自身lifespan内只收紧R02至read_file/list_files，其余无工具，拒绝Loop计划注册；原Loop和原生权限照常。真实消息/Steer/Stop未来只能Web页面；user Steer原文及首Chunk前提检查，记录真实来源、工具/队列事件、SDK及SSE发出时刻。DOM时钟另域，不能直接相减，必要时UNKNOWN。

新增30项Mock专项，与原Streaming97、旧UAT预算50、记账/Provider40共217项通过；不把历史1863当成本轮实际全量。compileall、JS语法、diff检查通过。新Chrome双profile Cookie/LocalStorage隔离通过，profile/探针清理；未操作8765或用户Chrome、旧Live库。真实DeepSeek/GLM/摘要/Judge0。

## 下一步与禁止事项

已完成预注册与冻结；最终状态OFFLINE PREPARATION PASS / LIVE BLOCKED，离线报告另提交并Push。不得重复prepare、freeze或重建账本，只允许未来按原路径verify和动态检查。只有未来明确GRANTED_8_REQUESTS且冻结与动态安全检查通过才运行R01→R04；本轮必须停在OFFLINE PREPARATION PASS / LIVE BLOCKED。

不复用旧授权/余额，不改冻结文本、评分、屏障、模型、端口、Fixture，不补跑，不切非流式求PASS。Provider支持/Usage/真实语义、实时DOM体验和真实取消仍UNKNOWN。屏障或跨时钟指标不可包装成自然首Token延迟。源码/审批/计数/数据/清理异常停止全批次。
