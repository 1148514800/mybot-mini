# Operator Reliability Hardening + Steer/Stop Canary v3

OFFLINE VALIDATION PASS / FREEZE PENDING / LIVE BLOCKED。LIVE_AUTHORIZATION: NOT_GRANTED，真实请求0；未来仅新GRANTED_2_REQUESTS有效。原T01 Semantic FAIL、T02 Startup FAIL、T03 BLOCKED和3/6、3011 Token证据不改判、不补跑。

原T02根因UNKNOWN。独立实验观察到TIME_WAIT与普通bind失败、connect无Listener但bind不可用等情况，仅证明机制差异，不能回溯证明历史根因。新操作员入口仅127.0.0.1、SO_REUSEADDR、无SO_REUSEPORT，单bind/listen后同一socket交Uvicorn；不释放探测socket后重绑。app factory及Attempt都在成功bind后，真实外部Listener测试拒绝且0 Attempt/SDK请求。ready在Uvicorn真实startup后发出，PID/UID/PPID/启动时间/cwd/argv/实际监听归属独立验证。

30/30原生Web同端口快速重启全部exit0，包含10轮活动SSE、30轮keep-alive；每轮端口重新可取得、Lease释放、无自有幽灵Listener。直接Server.run的SIGINT重新抛出只有在生命周期正常关闭已验证后才按uvicorn.run方式处理，不掩盖启动/清理错误。

浏览器关闭顺序已修复：Context仍在Playwright生命周期内关闭一次→driver退出→核对自己Profile的Chrome进程→核对真实目录身份后清理。主/启动/服务关闭/Context关闭/Profile清理错误分栏保留。正常与业务失败路径自动清理通过；Context关闭和删除故障注入如实FAIL，不因事后清理改为PASS。真实headed Chrome 152.0.7977.83，0700全新profile，双profile Cookie/LocalStorage双向隔离通过，用户Chrome/8765未操作。

N01/N02真实Chrome合成端到端PASS（实际SDK MockTransport，非真实Live）：N01真实DOM queued→not_applied、UI未生效及下一轮按钮可见、刷新/SSE重连后账本仍1；N02真实DOM Stop、SDK close、cancelled、terminal_trusted=false、Usage total=null、无重试/Fallback/工具，累计Mock请求2。两个Case同一固定Mock端口、两个服务exit0、SQLite/Lease释放，Profile自动清理通过。Mock结果不记为真实DeepSeek通过。

新句数模块识别相邻中文与旧T01结构的3句/期望2失败，不删改回复，不修改TaskContract。format_check、确定性计数与independent_semantic_review分开，复杂文本FORMAT_REVIEW_REQUIRED，不宣称通用语义正确性。

完整check_phase及独立补充专项通过：2097个去重unittest ID，实际执行2097次，去除重复0次；新增78项。check_phase程序式断言另已执行，不虚构为额外unit数量。不是沿用旧2051统计。compileall、JS语法与diff检查通过；源码前后hash与最终冻结证据分别保存。生产模块和旧UAT文件无修改，真实DeepSeek/GLM/摘要/Judge均0。

新唯一批次streaming-steer-recovery-v3-20261027、N01/N02各1/总2、固定8902，准备与冻结最终身份/提交见freeze-evidence.json；未授权维持0 Attempt/reservation/HTTP。后续真实not_applied/Stop行为、供应商Usage兼容与长时稳定性仍UNKNOWN。

见[t02根因](t02-startup-root-cause.md)、[socket设计](socket-lifecycle-design.md)、[清理证据](browser-cleanup-evidence.json)、[句数](sentence-diagnostics.md)、[预注册](n01-n02-preregistration.md)、[安全](security-audit.md)。历史资产、main/Tag/ZIP及共享AppleDouble旁文件均未处理。
