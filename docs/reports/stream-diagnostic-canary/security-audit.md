# Security and asset preservation

本轮没有真实模型授权，任何旧GRANTED_8/10_REQUESTS均不接受；Live入口在读取Provider配置、数据库或SDK之前检查精确新授权。Mock入口只使用httpx.MockTransport，完全不读取真实Provider配置。prepare仅本地读取原配置以验证模型/凭证存在及哈希，不请求Provider。

独立新worktree、分支、可丢弃workspace、两个私有SQLite；本批次唯一prepare/freeze，不重建、不替换。前置只读进程检查见旧uv launcher尚在但8765无监听；没有终止、重启、发送HTTP或更改其资源。8899空闲。不读取旧私有Live账本或会话，旧报告与生产代码/依赖通过git比较保持字节不变。

固定空Registry、关闭MCP/Skills/Coding/Steer/语义摘要；原Tool Authority、Cookie/Origin/CSRF/CSP不变。宿主测试门不向模型授予命令或文件权限。无真实工具调用。所有进程清理限于本次捕获并复核身份的Mock服务，未SIGKILL、批量pkill或删锁。

报告只含结构元数据、哈希、合成截图和计数。原生私有SQLite保留未来回复是持久化验收所需，不导出正文，不提交数据库/Profile/调试数据/密钥/Cookie/CSRF/nonce。完整模型Prompt、原始Chunk不落诊断文件。真实费用未知，不用估算Token充当Usage。

当前未发现未结算执行、文件污染或凭证暴露。该结论覆盖本次离线准备，不能担保未来Live执行；授权后必须重验冻结、进程、端口、Lease和浏览器身份。
