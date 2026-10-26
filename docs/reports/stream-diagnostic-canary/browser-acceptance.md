# Browser isolation and synthetic acceptance

真实本机Chrome152.0.7977.83、Playwright1.64.1、headed、chromium_sandbox=True。两个新0700非符号链接profile访问同一非生产Origin，A/B测试Cookie和LocalStorage双向不可见；实际Chrome argv的user-data-dir与UID核验。无读取/复制用户Cookie，未操作8765页面或原Chrome。

独立第三个新profile进行两次临时Mock服务验收。DOM点击新会话、填入固定消息、点击send；只读状态核验，未伪造后端结果。MutationObserver只读DOM，以同一performance.now时钟记录点击到可见预览：正常约263.7ms，拒绝样本约262.3ms。这些是Mock延迟，不是DeepSeek性能。原生EventSource在关服时仍打开，两个子服务均正常exit0，随后端口释放。

截图只截合成预览和非生产探针，没有私人回复或Cookie。正式D01 profile将在授权后的执行前另建并再次核验，当前探针/演练profile都已清理。浏览器双profile隔离通过不自动授予Live。
