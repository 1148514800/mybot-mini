# Live security audit

授权精确GRANTED_1_REQUEST，原冻结verify在启动和发消息前通过，服务内部每次SDK/HTTP准入持续核验。唯一原prepare/freeze没有重做，生产源码、依赖、Web安全实现、冻结消息/配置/参数/评分均未修改。仅新增本次Live报告并更新当前状态文档。

原始初始占用断言把当前校验进程自己的只读SQLite句柄也计入。复核lsof持有者仅为该校验PID，原进程退出后句柄消失；未发现其他进程持有批次，未改变资产来消除断言。此前断言失败未启动服务、Attempt或模型请求。证据保留在preflight。

预算ledger1 reservation/1 HTTP/1 Attempt，均为coco；无备用、隐式重试、摘要、Judge、工具或额外请求。状态failed，HALT diagnostic_failed不清除，普通verify明确拒绝HALT，cleanup只允许已有资源清理不授予新准入。

关闭自身服务正常SIGINT，wait exit0，两个自有PID已退出、端口释放、Lease可获取、库integrity ok、无uncertain/unsettled。profile清理。未操作旧8765 launcher/页面、用户Chrome、旧私有数据库或旧HALT；不对更早用户内存会话作未经检查的保证。

报告不含完整请求/模型正文/原始Chunk、API Key、Cookie、CSRF、Receipt、nonce、浏览器profile或私有SQLite。仅发布安全ring、Usage字段、计数、来源hash和脱敏终态截图。预览图的动态mask竞态在提交前发现并删除，不把未完整脱敏图当作公开证据。

SDK观察Usage不等于可信结算账单，输入估算不替换供应商Usage。未发现不确定执行或workspace文件污染；数据库新增一轮用户/助手事件是预期运行数据，不提交数据库。
