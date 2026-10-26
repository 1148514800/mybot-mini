# D01 — OFFLINE PREPARATION PASS / LIVE BLOCKED

LIVE_AUTHORIZATION: NOT_GRANTED。真实请求0/1，Attempt0、reservation0、HTTP0。D01没有运行；不能把本轮Mock或浏览器演练判成真实Streaming PASS。DeepSeek/GLM/摘要/Judge均0，供应商Token未知且未请求，cost=null。

独立分支codex/stream-diagnostic-canary以ba759de36418d67008e98c8c7ddf05566dc520e5为基线。新单次请求harness已实现，唯一prepare完成；此预注册提交时freeze待执行，最终冻结证据由独立Acceptance提交补充。禁止改动原HALT/旧结果。

252项去重测试PASS（新增33；39协议、11关闭、8SSE、33Streaming、12Streaming failover、30Web/Steer、30旧UAT离线预算、23Accounting、17Provider failover、16Token预算）。最后新增导出model/opening error字段后33项再次通过，重复执行不重复计数。compileall、JS语法和git diff --check通过。本任务没有重新声称上一轮1951项已经全量重跑。

双profile真实Chrome152.0.7977.83 headed验证Cookie/LocalStorage双向隔离，独立临时profile完整清理。另一个全新profile通过DOM发送D01固定文本到MockTransport服务：正常流protocol PASS、重复终态正确protocol FAIL，两次各1个Mock HTTP；两种情形打开EventSource时均exit0，端口/Lease释放、SQLite一致。浏览器演练只验证机制；没有读取/导出原用户Chrome、旧聊天或旧私有Live数据库。

正常Mock四块，stop一次、自然EOF与SDK close成立，SQLite最终助手文本哈希匹配。重复终态Mock四块，stream_duplicate_finish、Chunk4、非自然EOF、SDK close成立，不能可信完整保存；HALT保留，仍正常关闭。首Chunk前503的Mock备用准入被单次预算拒绝，只有1 reservation/1 HTTP；首Chunk后中断不Fallback。缺Usage样本protocol PASS而Usage UNKNOWN，关闭失败样本保留reserved/HALT。

真实D01的finish/EOF/错误/首Chunk/UI延迟/Usage/退出码均NOT_RUN或null。当前只解除离线机制准备问题；未来必须有新的GRANTED_1_REQUEST并verify。即使新D01成功，也不能改变旧R01 FAIL或保证长期兼容。
