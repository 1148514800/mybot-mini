# Isolated Chrome Live operation

当前再次运行非生产同Origin双Profile Cookie/LocalStorage双向隔离测试，通过且两profile清理。然后另建第三个全新0700非符号链接profile，Chrome152.0.7977.83 headed、sandbox开启，初始Cookie Jar为空，实际UID/argv user-data-dir匹配，未使用默认用户profile或导入Cookie。

只访问127.0.0.1:8899，未操作8765或设置/凭证。原页面自动创建一个空session后，DOM点击新会话并填入唯一冻结消息，点击send一次；message POST202。只读状态核验；消息从真实DOM发出，不构造后端写API。Steer0、工具0、无重发。

只读MutationObserver使用performance.now，同一页面点击970.9ms、首次可见3470.9ms，相差2500.0ms；随后轮询确认预览存在时服务仍running。未修改模型内容或提示。SSE宿主emit记录不是浏览器接收时刻，跨时钟差值UNKNOWN。

终态界面provider_error，活动面板显示供应商状态异常、逻辑请求1、Usage未知。服务关闭时保留原生EventSource，wait取得exit0。只关闭本次Chrome，profile清理，无Cookie冲突证据。

审查发现预览mask与动态正文增长有竞态，截图有未完全遮蔽的正文行；该自建临时图已丢弃并删除，没有提交。仅发布无回复正文的终态活动面板截图，敏感面板/时间线遮蔽。没有为了截图补发或重启。
