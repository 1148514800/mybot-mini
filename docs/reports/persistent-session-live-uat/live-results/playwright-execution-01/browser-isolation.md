# Browser isolation

Python Playwright 1.64.1通过仓库外临时uv环境运行；没有修改pyproject.toml、uv.lock或项目虚拟环境。复用本机Chrome稳定版152.0.7977.83，真实headed页面，chromium_sandbox=True。使用launch_persistent_context(executable_path=现有Chrome,user_data_dir=新mkdtemp目录,headless=False)，而非普通窗口或sessionName。

本地非生产Origin探针创建A/B两套全新0700非符号链接profile。初始均无测试标记；A的Cookie与LocalStorage只有A能读，B写入后A仍看不到B，两侧独立。真实进程参数均核对到各自准确user-data-dir；点击、输入、DOM和截图有效。只用专用合成标记，没有MyBot Cookie或用户数据。探针关闭、两profile清理。

通过后另建第三套全新UAT profile，启动PID49832的实际参数再次核对，Cookie Jar初始为空，专用于127.0.0.1:8889。L03重启获取新的认证Cookie及CSRF，证据只记录变化布尔值，不导出值。最终context.close关闭自己的实例并移除自己的profile，用户Chrome PID56352继续存在。

未打开8765、用户默认Chrome profile或设置页，没有复制Cookie、修改Origin/CSRF/浏览器安全策略。完整脱敏元数据见browser-isolation-evidence.json；A/B截图是非生产探针。
