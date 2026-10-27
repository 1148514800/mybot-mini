# Browser and shutdown

本机现有Chrome152.0.7977.83、Playwright临时环境、headed且sandbox开启；不修改项目依赖或原Chrome。两个全新0700 profile访问同一非生产Origin，Cookie/LocalStorage双向隔离，实际UID/argv user-data-dir核验通过并清理。第三新profile运行原生Web Mock演练。

T01 DOM新Session/发送/Steer一次；T02新Session/自然首块Steer、not_applied提示并真实刷新，未重发模型；T03新Session/首块后Stop。消息、Steer、Stop没有后端写API替代。只读状态与SDK文件核验实际层级。

三次自有服务保持EventSource时正常SIGINT/wait exit0，端口/Lease释放、SQLite一致、所有SDK owner关闭；只关闭自己的Chrome/profile。截图只含安全终态面板及非生产探针。SDK/浏览器时钟不相减，屏障耗时不算自然Provider延迟。Live未运行、真实清理仍待新授权验证。
