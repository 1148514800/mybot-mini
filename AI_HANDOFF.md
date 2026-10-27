# AI_HANDOFF

## 当前状态

codex/streaming-operator-reliability-v3，基线e9d04f2c28fb46c0216df362170beaeaeccd452d。Operator Reliability离线实现/验证完成，唯一新N01/N02 prepare/freeze/verify及离线Acceptance完成。LIVE_AUTHORIZATION NOT_GRANTED，真实DeepSeek/GLM/摘要/Judge0，不继承旧v2剩余3次。

## 实现与验证

只增scripts/uat_operator/、scripts/streaming_steer_recovery_v3/和4专项，不改mybot生产、依赖或旧UAT源码。单127.0.0.1 SO_REUSEADDR/no REUSEPORT bind/listen后同socket交Uvicorn0.54 Server.run，bind失败在app/Attempt之前；ready与实际子进程监听身份分别验证。30轮同端口原生Web重启全部exit0（SSE/keep-alive）、端口可重新取得、Lease释放；外部Listener和bound非listen冲突拒绝。原T02根因仍UNKNOWN；本轮独立TIME_WAIT机制复现不回溯原故障。

Context仅在Playwright有效期间close一次，再核实本profile进程退出/目录dev-inode-UID-非symlink后清理；主/服务启动/服务关闭/Context/Profile错误分栏，错误注入不掩盖主因或伪报自动PASS。headed Chrome正常N01/N02共用同端口、2 SDK Mock HTTP、2服务exit0/profile自动清理；双profile Cookie/LocalStorage隔离与8种headed异常路径证据。N01 queued→not_applied/UI/刷新无重发，N02 Stop/cancelled/SDK close/untrusted部分/Usage null。句数分确定性/格式/独立语义，旧T01结构复现3句FAIL，复杂文本需review。

完整check_phase及独立补充2097去重unittest PASS，新增78，程序式断言另执行不乱加计数；原Streaming/Steer/工具配对/权限/来源/持久化/预算回归保持，源码前后hash一致。compileall/JS/diff检查PASS。报告docs/reports/streaming-operator-reliability-v3/。

## 下一步与边界

Implementation 07c25ce181b2af3dc368815ec4956a3ff05c75a2，Preregistration/冻结源码 4a8fdb64a22811b20aebb85d1e1d25e9f385ad67。~/.mybot-mini/uat/streaming-steer-recovery-v3-20261027/已唯一prepare/freeze/verify，端口8902，N01/N02各1/总2。320源码hash/原配置/workspace/两库inode及完整性通过，0 Attempt/reservation/HTTP、事件库空、Lease可用。freeze后不得改源码或再prepare/freeze。未来必须新精确GRANTED_2_REQUESTS和原冻结/环境/浏览器身份检查，不补跑旧T02/T03、不复用旧余额。当前Mock不代表真实DeepSeek not_applied/Stop成功。

旧T01 Semantic FAIL、T02 Startup FAIL、T03 BLOCKED、3/6/3011 Token/原HALT私库均保留；旧Chrome/8765未操作。main/历史Tag/ZIP与共享Git AppleDouble旁文件不处理。验收结果已固定；最终提交/远程HEAD通过Git确认。后续只能在新授权门继续。
