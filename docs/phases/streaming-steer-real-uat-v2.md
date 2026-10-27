# Streaming Tool Call & Steer真实UAT v2准备

未编号工程专题，不创建或移动历史Phase Tag/ZIP。

目标：区分用户补充被接收、主机准入、预算预留、HTTP发送、模型响应和语义遵从。SteerInbox的applied在原on_dispatch触发，可以发生在后续HTTP失败之前；它不代表修改在途请求，也不代表模型理解。

流程：plan冻结T01/02/03原文、Fixture与6总额/4-1-1；prepare建立独立workspace/两库并冻结原配置/源码/identity；budget复用原持久schema/HTTP门；server复用create_app→Runtime→AgentLoop→ProviderFailover；adapter透明观察真实SDK，先yield首块再定时屏障；evidence在受控内存比较Source ID/原文/消息hash与工具配对；browser用新profile真实DOM；mock只改变供应商测试传输，所有HTTP都由MockTransport拦截。

核心语义：T01 Steer在工具开始前排队，原AgentLoop生成executed=false工具结果并保留配对，再将可信用户reference加入下一请求。工具仍由原ReadOnly Registry/权限执行，不包装工具或扩权。T02无下一请求时not_applied；T03取消关闭而不可信部分。Observer在native close后的下一SDK入口/Turn结束才结算，避免早于可信终态提升级别。

macOS/Python3.12+/uv：`uv run python -m scripts.check_streaming_steer_real_uat_v2`；独立Chrome用`uv run --no-project --with playwright python -m scripts.streaming_steer_real_uat_v2.browser --chrome <现有Chrome> --output <新私有目录>`，默认Mock。prepare/freeze/verify命令见预注册；未来--live须新精确GRANTED_6_REQUESTS且先核验隔离/端口/Lease/库。生产依赖/SDK不修改。

本次相关388去重测试（新增47），不称2051全量重跑；三个Chrome合成场景5次Mock模型HTTP、三个服务exit0，真实0。首轮元数据字段重名在UAT内修复，配对证据增加批次索引。常见误区：queued/applied/HTTP/返回/遵从不等价；8秒屏障不是Provider延迟；stop/GeneratorExit不是EOF；空场景前提不能用补问制造成功。

最终状态见[报告](../reports/streaming-steer-real-uat-v2/acceptance-report.md)。原R01/D01/D02不改判，下一步仅新授权后的原冻结Live，不复用旧额度。
