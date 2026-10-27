# Streaming Tool Call & Steer真实UAT v2准备

未编号工程专题，不创建或移动历史Phase Tag/ZIP。

目标：区分用户补充被接收、主机准入、预算预留、HTTP发送、模型响应和语义遵从。SteerInbox的applied在原on_dispatch触发，可以发生在后续HTTP失败之前；它不代表修改在途请求，也不代表模型理解。

流程：plan冻结T01/02/03原文、Fixture与6总额/4-1-1；prepare建立独立workspace/两库并冻结原配置/源码/identity；budget复用原持久schema/HTTP门；server复用create_app→Runtime→AgentLoop→ProviderFailover；adapter透明观察真实SDK，先yield首块再定时屏障；evidence在受控内存比较Source ID/原文/消息hash与工具配对；browser用新profile真实DOM；mock只改变供应商测试传输，所有HTTP都由MockTransport拦截。

核心语义：T01 Steer在工具开始前排队，原AgentLoop生成executed=false工具结果并保留配对，再将可信用户reference加入下一请求。工具仍由原ReadOnly Registry/权限执行，不包装工具或扩权。T02无下一请求时not_applied；T03取消关闭而不可信部分。Observer在native close后的下一SDK入口/Turn结束才结算，避免早于可信终态提升级别。

macOS/Python3.12+/uv：`uv run python -m scripts.check_streaming_steer_real_uat_v2`；独立Chrome用`uv run --no-project --with playwright python -m scripts.streaming_steer_real_uat_v2.browser --chrome <现有Chrome> --output <新私有目录>`，默认Mock。prepare/freeze/verify命令见预注册；未来--live须新精确GRANTED_6_REQUESTS且先核验隔离/端口/Lease/库。生产依赖/SDK不修改。

本次相关388去重测试（新增47），不称2051全量重跑；三个Chrome合成场景5次Mock模型HTTP、三个服务exit0，真实0。首轮元数据字段重名在UAT内修复，配对证据增加批次索引。常见误区：queued/applied/HTTP/返回/遵从不等价；8秒屏障不是Provider延迟；stop/GeneratorExit不是EOF；空场景前提不能用补问制造成功。

原离线状态见[报告](../reports/streaming-steer-real-uat-v2/acceptance-report.md)，历史保留。原R01/D01/D02不改判。

唯一prepare/freeze已完成，冻结源码SHA 6337a20ae926f28cae0446f5e008bc754d2e14e0；原离线Acceptance时0请求且停在NOT_GRANTED。

新GRANTED_6_REQUESTS后唯一Live：T01真实三请求，Tool/Steer链路及协议通过，完整回答3句违反两句要求，Task/Semantic FAIL；T02启动bind EADDRINUSE/exit1，在Attempt前失败；T03未执行，整体部分执行FAIL/余项BLOCKED。DeepSeek3、GLM/摘要/Judge/重试0，Token2834/177/3011，cost=null。T01exit0，T02不能称清理PASS；浏览器异常清理次级错误后仅核实并移除自有profile，最终资源已释放、无uncertain或workspace污染。原冻结302源码/配置/两库身份/元数据hash保持，0未结算。

[Live报告](../reports/streaming-steer-real-uat-v2/live-results/execution-01/acceptance-report.md)包含分层来源/HTTP/协议/语义/清理证据。案例教训：applied不是模型遵从；用途准确不等于格式遵从；connect无监听不能证明下一plain bind必可用；finally在Playwright退出后再close会掩盖原始启动异常。SDK观察句数2有中文相邻句漏计，独立审阅3，不改历史字段。后续另立修复和新授权批次，不能用余额或原Case补跑。
