# 独立headed Chrome合成验收

新0700 Profile，实际launch user_data_dir/UID/空Cookie/sandbox核验；先用两新Profile同Origin执行Cookie/LocalStorage双向隔离，关闭自己的probe和清理目录。使用本机Chrome152.0.7977.83 / Playwright1.64.1，不修改默认用户Chrome或8765。

最终验收使用固定127.0.0.1:8903，未因冲突随机换端口。Native Web真实DOM新建会话/发送冻结任务；SDK MockTransport逐块返回工具调用，由原AgentLoop读取测试/源码、预览、Receipt提交、运行测试及最终回复。页面实际观察pre.diff、命令审批弹窗、当前Coding状态和Revision；批准标为SYNTHETIC_APPROVAL，明确检查有效argv/cwd/超时/沙盒后点击一次。

Controller verified、Revision1、实际Patch1、当前版本公开测试5项通过；在进程隔离评分目录执行Public5/Host10全部通过。六次Mock SDK/HTTP，不是真实DeepSeek调用。human_command_approval=false/strict_success=false正确保留；synthetic_workflow_pass=true。

刷新并等待2.3秒超出原有限SSE周期，仍6次持久请求；无重发模型/重做Patch。服务wait exit0、无Listener、SDK流关闭、SQLite完整、Lease释放，Context在Playwright活跃期间关闭一次，自有Chrome退出/Profile自动清理。审批截图遮罩完整argv详情中的私有运行路径；实际DOM内容已在受控内存检查，不导出nonce。终态截图遮罩timeline/Pin/contract，不提交原始模型回复或Receipt。
