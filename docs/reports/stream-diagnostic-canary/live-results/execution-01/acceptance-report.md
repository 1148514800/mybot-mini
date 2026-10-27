# D01 Live — Protocol FAIL / Clean Shutdown PASS

在本轮明确GRANTED_1_REQUEST后，从输入HEAD `506ea5ba6289994b3de31bed3a409b2d57057ad6`执行唯一D01。Preregistration/source SHA `c87a26b3532a640b4c604b5870c5bf638c095960`，分支codex/stream-diagnostic-canary。复用原唯一冻结批次、配置、workspace、两库和合同；未重新prepare/freeze、改源码、改消息/参数/评分或补跑。

真实1/1次物理、1次HTTP、1个Attempt，coco / deepseek-v4.1-flash；GLM、fallback、重试、模型摘要、Judge均0。通过新0700独立headed Chrome真实DOM新会话、填入冻结消息、点击发送一次，HTTP202。正式create_app→ChatRuntime→AgentLoop→ProviderFailover→SDK路径，空Registry与Steer关闭保持。

收到221个SDK Chunk；第221块在protocol_validation触发固定代码`stream_after_finish_payload`，consumer和Web终态provider_error。结构ring最多8块，无正文/参数。观察到stop一次，但accepted finish为null、terminal_trusted=false，natural_eof=false、SDK close=true，最终持久回复不具可信完整性。Case failed、reservation failed且结算，HALT=diagnostic_failed保留，未重试或追加请求。

错误码定位了拒绝点，却不能单独归责供应商或宣称“stop后继续输出正文”。第221块摘要为role存在、空字符串content、tool_calls_count=0、stop；原实现将旧式function_call真值与终态后负载共用同一码。结合唯一终态观察和accepted finish null，代码可达性推断指向function_call真值分支；但ring没记录此字段或原始对象，不能确认字段内容、SDK解析影响或责任。详见protocol-diagnostics。

首SDK Chunk约1.725s，首文本约1.726s，首SSE宿主预览emit约2.368s；同一浏览器performance.now提交到首次可见预览2.500s，且在running时观察到。跨SDK/DOM时钟延迟UNKNOWN。UI预览局部PASS不代表协议成功。

观察器记录供应商数值字段输入480、输出219、总699 Token；这些来自SDK Chunk，非输入估算。但未取得自然EOF，原consumer/ledger把结算Usage保留为全null。观察字段齐全不等于可信完整Usage；Usage兼容维度UNKNOWN，真实结算/账单无法核对，cost=null。禁止把UI显示的估算输入2726当成供应商Usage。

本次自有launcher与子服务正常退出，operator wait exit0，约1.518s；SDK流关闭、8899释放、Lease可获取释放、SQLite一致，无未结算reservation或execution_uncertain。Chrome profile清理。新HALT未清除；只读核验确认新请求准入拒绝。Clean Shutdown PASS，且不改变Protocol FAIL。

冻结prepared/freeze/探针hash、源码、原Provider字节、workspace字节/inode、两库inode均保持。库中2个session来自原页面自动空会话与显式独立D01会话，只有1个turn/Attempt、2条消息、0工具。旧8765 launcher未操作，旧私有HALT数据库未打开；所有旧结果不改判。

浏览器遮蔽预览截图有DOM增长竞态，审查后丢弃并删除该自建临时图片，只提交无回复正文的终态活动面板截图；没有为截图重新启动服务或再发消息。本次诊断保留缺陷与证据局限，不制造Streaming PASS。冻结额度已用尽，不能继续Steer或旧R01–R04。
