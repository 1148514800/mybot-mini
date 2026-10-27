# Isolated Chrome real D02

当前再次进行非生产同Origin双profile Cookie/LocalStorage双向隔离，通过且两个profile清理。随后第三个全新0700非符号链接profile用于D02：Chrome152.0.7977.83、headed、sandbox开启，初始Cookie Jar为空，真实UID/user-data-dir核验，无默认profile或Cookie导入。

只打开127.0.0.1:8900。原页面自动空会话后，真实DOM点击新会话、填入原文、点击send一次，POST202；状态接口只读核验，不构造写消息API。Steer0、工具0、无重发。原Cookie/CSRF/Origin边界保持。

只读MutationObserver以同一页面performance.now记录submit950.6ms、visible3650.6ms，差2700.0ms；轮询在running时确认预览可见。终态观察7524.1ms是带轮询误差的观察值，不当作精确SDK完成时间。首SSE宿主emit使用另一个时钟域，跨钟延迟UNKNOWN。

为避免上轮动态mask竞态，不捕获预览正文截图；仅在终态稳定后保存活动面板，遮蔽时间线/Pin/Contract，人工检查无模型正文或Cookie。页面显示模型回复返回、逻辑请求1、已报告987 Token。关闭服务时保留EventSource，wait exit0，随后只关闭自己的Chrome并清理profile。未访问8765、用户Chrome或旧会话。
