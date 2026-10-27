# D02 Live — Protocol PASS / Clean Shutdown PASS

本轮收到精确GRANTED_1_REQUEST后执行唯一D02，输入HEAD `18f89ddd63e1b5fe6d429424cdcd5a6f3e520450`，Preregistration/冻结源码 `06d53077c3f35985506c835b42d29fd8cd394aa7`，分支codex/stream-legacy-function-compat。复用原唯一新批次、原Provider、workspace、两库、消息、配置和评分；未重新prepare/freeze、改源码/参数/消息或补跑。

实际1/1次物理、1次HTTP、1个Attempt，coco/deepseek-v4.1-flash。GLM、Fallback、重试、摘要、Judge、工具、Steer均0。新0700独立headed Chrome真实DOM发送唯一消息，POST202；正式create_app→ChatRuntime→AgentLoop→ProviderFailover→SDK路径及所有预算门保持。

514块真实SDK Chunk，最后一块stop观察与接受各1次、无错误码；自然EOF=true、SDK close=true、terminal_trusted=true，最终stream_status=complete，Web/turn completed。SQLite正式助手文本与SDK拼接/原生strip哈希一致，原始与规范化hash本次也相同，可信完整持久回复PASS。

第514块具有实际legacy结构证据：字段存在、kind=object，name与arguments均string且长度0，extra_count=0，semantically_empty=true；content空字符串、tool_calls数量0。修复后的字段语义检查正确允许该空对象，再接受stop并自然EOF。这证明本次部署样本的空legacy兼容，不还原D01原字段、不改变旧R01/D01 FAIL，也不保证所有部署/版本/工具协议。

首SDK Chunk约2.280秒，首文本2.281秒，首SSE宿主emit2.563秒；同一浏览器performance.now点击至首次可见文本2.700秒，且在running阶段观察到。跨时钟SDK→DOM延迟UNKNOWN；无人工时序屏障。预览成功与协议完整性独立评分。

观察与可信结算Usage一致：输入475、输出512、总987 Token，非输入估算；SDK observer、原ledger和页面987相互一致。没有可信部署价格或账单核对，cost=null，不能由Token直接给出实际费用。未记录Usage具体Chunk索引，不声称它一定来自独立空choices尾块；独立尾块支持已由离线测试覆盖。

服务在EventSource仍打开时正常SIGINT、wait exit0，约1.114秒；两个自身PID均退出、8900释放、SDK关闭、Lease重新可获取、SQLite一致，0 unsettled/0 execution_uncertain。Chrome profile清理，未操作用户Chrome或8765旧服务。

内容格式另有不足：912字符最终文本按空行分为7个单行块，均非标题/代码块，未严格满足输入“五个自然段”的格式要求。该附加格式观察记录FAIL，不修改冻结的独立Protocol PASS；整体内容语义没有独立评审，不能把本次协议PASS包装成所有任务遵从PASS。

Case passed、reservation returned、无HALT；额度与唯一Attempt已耗尽，不能再启动D02或继续Steer。2个session是原页面自动空会话和显式D02会话，只有1个turn、2条消息、0工具。冻结资产hash、源码、Provider字节、workspace字节/inode及两库inode均保持，原失败与离线报告原样保留。最终报告提交、远程HEAD以交付核对为准。
