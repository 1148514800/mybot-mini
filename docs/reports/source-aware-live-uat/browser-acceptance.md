# Browser readiness

非生产双profile隔离PASS：Python Playwright1.64.1、headed Chrome152.0.7977.83，chromium_sandbox=True。A/B均全新0700非符号链接目录，实际进程UID与独立user-data-dir核验；初始Cookie Jar为空。在相同127.0.0.1 Origin，A的专用Cookie/LocalStorage标记B不可见，B写入后A仍不可见。点击、输入、DOM和两截图有效；自己的Chrome进程退出、profile和本地探针服务清理。

没有新标签/sessionName模拟身份隔离，没有导入用户Cookie、操作原8765、默认Chrome profile或用户聊天。生产Cookie/Origin/CSRF/CSP完全不改。探针只使用合成标记，非MyBot认证Cookie。

真实S01–S03浏览器执行BLOCKED（NOT_GRANTED）。Mock Web流程通过ASGITransport，是离线测试，绝不冒充真实浏览器Case验收。获新授权后须再建专用0700 Live profile并核验PID/身份/端口/资源；不会复用已删除的探针profile。
