# Browser isolation PASS; R01 preview observed

Python Playwright1.64.1，Google Chrome152.0.7977.83，headed、chromium_sandbox=True。动态两个新0700非符号链接profile访问同一非生产Origin；A/B各自Cookie与LocalStorage均双向不可见；输入、点击、DOM、截图验证通过。二者进程UID/实际--user-data-dir核验，探针/profile均清理。

之后另建全新私有UAT profile，启动命令核验，初始Cookie为空。通过真实8899页面点击新会话、输入唯一冻结R01消息、点击发送。浏览器MutationObserver只读取预览DOM及performance.now，不写应用状态，不关闭CSP/CSRF/Origin。首次预览显示114字符与“生成中 · 临时预览，尚未正式保存”，发生在最终错误前。

临时operator首次以无TTY启动，stdin立即EOF，仅打开并关闭空新profile，未启动任何Case或Provider；改为TTY后的新profile才实际执行R01。这不是Case补跑。运行过程中只读API核对状态，没有API写入冒充页面操作。

R02/03/04全部未启动，未发送Steer或Stop，不能以合成测试替代Live。最终关闭自己Chrome并移除新profile；用户原Chrome及8765均未触碰。截图只含合成探针标记和本轮资源数字，不含完整模型回复、Cookie、CSRF、私有用户聊天或调试数据。

SDK到DOM跨时钟差值UNKNOWN；浏览器DOM观察时间也不是合成器像素首次绘制的精确时刻。
