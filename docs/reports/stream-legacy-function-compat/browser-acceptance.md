# Headed Chrome synthetic acceptance

全新0700非符号链接双profile、同一非生产Origin，Cookie和LocalStorage双向隔离通过。Chrome152.0.7977.83、Playwright1.64.1、headed、sandbox开启；实际PID/UID/user-data-dir核验，无用户默认profile、无8765页面。

另一全新profile通过原Web入口和SDK MockTransport测试：

|场景|观察结果|
|---|---|
|A 空legacy，无Usage|运行中可见预览，可信complete、EOF/close，Usage未知|
|B 非空函数名|legacy_unsupported、0工具，失败符合预期|
|C stop后正文|after_finish_payload，仍拒绝|
|D 标准Usage尾块|运行中预览，自然EOF、close、可信Usage|
|E 浏览器Stop及关闭|原生Stop取消，未重试；保留EventSource，服务exit0|

A–E每个临时服务各1次Mock HTTP，5次服务wait exit0、端口与Lease释放、SQLite一致、profile清理。B/C/E的产品FAIL是预期安全拒绝，验收通过不把它们改为产品成功。

独立Steer浏览器A–H合成回归10次Mock HTTP：queued→applied、原请求哈希未变/下一请求含Steer、未启动旧工具配对跳过；queued→not_applied不产生额外请求；关闭/恢复不重放旧调用。两次自有服务wait exit0。所有模型HTTP由MockTransport拦截，真实Provider0，原Chrome和服务未操作。截图只含公开合成内容，完整细节见浏览器证据JSON。
