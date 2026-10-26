# Streaming protocol diagnostics and graceful shutdown — OFFLINE PASS

本阶段真实模型授权0；DeepSeek、GLM、语义摘要、Judge均0。输入2b08360ee87aba28a9935f8a2b06fae2467883b4，独立分支codex/streaming-protocol-shutdown-fix。Implementation：`d73e31a599fc222d35f782474ddae70e3dbf12c6`；Acceptance Commit与远程HEAD在最终交付核对。

ORIGINAL_R01_ROOT_CAUSE: UNKNOWN

原328个Chunk缺少完整结构，不能精确重放或把GeneratorExit归责网络，也不能从stop推断EOF。本轮保持原R01 FAIL、后续BLOCKED与原HALT/running/1次请求，不使用剩余7次。

## 实现结果

- streaming.py增加固定错误枚举和StreamProtocolError；单次物理record最多8块结构元数据，记录阶段、块序号、终态次数、自然EOF与close。原始文本、参数、完整Chunk、SDK异常正文不进入诊断；SSE只传固定错误码。
- 可信完成明确要求合法finish＋SDK自然迭代结束＋close确认。标准空choices Usage保持支持，重复终态／终态后输出严格拒绝；无DeepSeek特定宽容或非流式回退。预算/存储/未知宿主异常不吞成普通Provider错误。
- server.py的2秒SSE连接及250ms原生重连打破Uvicorn drain→lifespan→runtime.closed循环等待，保留Last-Event-ID/reset即时语义；断连不停止后台模型或重发请求。
- runtime.py保持同Task的MCP/SDK清理deadline；HALT不能阻止清理已拥有任务。操作员local_web_process核实PID/UID/PPID/出生时间/argv/cwd/端口，修复继承TTY时launcher未转发SIGINT的关闭流程；没有强杀或清HALT。
- Web以安全代码补充“协议结构不兼容／流中断／关闭状态未知”等说明，不广播完整ring或私有异常。

## 验证

固定Implementation上的完整check_phase：59 suite、1734项PASS；原独立补充129项、原新UAT预算30项、新协议39＋关闭11＋SSE8项均PASS。按真实test ID去重总1951项；重复开发运行不重复计数，非unittest帮助检查与Chrome场景不混入数字。compileall、app.js/markdown.js语法和diff检查PASS。原Streaming33、Failover12、Inbox22、Web Steer30包含在1734内，不另加。

独立headed Chrome A–G全部PASS，最终9次Mock HTTP、真实0；逐场景DOM hash与SDK请求hash已保存。继承TTY且浏览器保持连接：活动流服务约1.777秒、HALT服务约3.285秒exit0，端口/Lease释放；自身Chrome/profile清理。完整工具可执行、不完整工具不执行；Steer queued/applied分离，后续请求包含补充，原请求不变；重启不重放旧流/工具/Steer，不保存部分回答为完整assistant。

额外独立SDK MockTransport＋原observer实验准确产生“stop→本地duplicate_finish拒绝→observer GeneratorExit”；新consumer记录真正的块序号和拒绝原因。401块合法流通过，证明没有328块数量门。此实验不是原R01根因证据。

## 保留的限制

合成成功不能宣称真实DeepSeek协议已修复。SSE周期重连有短间隙与连接开销；清理deadline是合作式，不能强制终止不响应取消的协程；原OSError及CancelledError单独不足以推断远端网络或用户意图。原冻结UAT入口保持不改，后续须用全新批次、账本与明确新授权。

证据分类见r01-evidence-analysis；taxonomy、synthetic-reproduction、shutdown-analysis、browser-acceptance、security-audit与remaining-risks分别记录。原Live报告和冻结资产没有改写。提交仅实现、专项脚本和脱敏文档/截图，不含私有数据库、Profile、Cookie、密钥、Prompt或私有模型响应。
