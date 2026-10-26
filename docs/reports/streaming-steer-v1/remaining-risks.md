# Remaining risks

- 真实DeepSeek/coco和GLM/coco2部署是否支持stream_options、Chunk规范、Usage及中断行为均UNKNOWN；只验收SDK与合成协议。不能宣布真实Provider通过。
- 单choice纯文本/函数工具v1，不支持音频、多choice、废弃function_call或任意非标准协议。未知结构失败关闭，不自动重试。
- 行缓冲隐私策略会增加首预览延迟，长行和长不透明标记可能过度隐藏；不保证每字符立即显示，也不是通用秘密语义检测器。
- applied表示加入下一次准入请求，不代表供应商收到/成功或模型遵从。持久事件和远程HTTP之间没有分布式事务；崩溃可能留下已准入但远端结果未知的尝试，绝不重放。
- 当前实现单进程Turn所有权；重启不恢复Inbox，已有其他进程的活动任务不能通过此服务Steer。部署时不能让不理解新Steer schema的旧写者共享活动库。
- Steer不更新TaskContract可信要求，不创建Pin，不把补充当原始user_input；以后Turn不会自动当作当前指令重放。需要持久决定时仍用原显式Pin操作。
- 用户在工具已开始后补充不能撤销已经发生的副作用。清理未知时继续保留Lease和安全阻止，不能为了UI顺畅冒称安全结束。
- 完整输出状态不是业务正确性；Source Preservation和Decision Provenance的原语义边界、助手影响UNKNOWN均保持。
