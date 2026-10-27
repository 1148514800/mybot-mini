# OFFLINE PREPARATION PASS / LIVE BLOCKED

LIVE_AUTHORIZATION: NOT_GRANTED。本轮真实DeepSeek/GLM/摘要/Judge请求均0，T01–T03 Live未执行，唯一Live批次已prepare/freeze，0 Attempt/0 reservation/0 HTTP，事件库空。旧D02已耗尽的授权不继承。

独立分支codex/streaming-steer-real-uat-v2，基线54eeeb80be0cdef65f25affc6eae6c907474cb19。只新增UAT与报告，生产mybot、静态JS、依赖及旧脚本/报告均未改；保留旧R01/D01/D02真实成绩、HALT与私有库，不合main、不改Tag/ZIP。合同原文和评分见preregistration.md。

最终源文件上388项去重相关回归PASS，新增47；原Streaming33、Failover12、Steer22、Web30、Accounting23、Provider17、Token16、协议39、关闭11、SSE8、旧UAT30、D01门33、D02门33、Legacy34均实际运行。没有把历史2051当成本次全量重跑。权威运行前后源码hash一致；compileall/JS语法/diff通过。首轮新UAT元数据字段重名故障已修复并保留日志hash，未删断言或改生产。

真实SDK MockTransport+原生Web验证了：6总额/4-1-1 Case限额、并发与重启、唯一Attempt/顺序、HALT/未结算门、SDK retries0、预算前/HTTP前两层计数、工具分块/合法跳过配对、Steer来源/原文进入下一实际请求、原请求未改、无下一步not_applied、取消close、无EOF不可信Usage、HTTP失败时applied不等于dispatched。专门异常样本证明applied可在HTTP0时成立；不完整工具参数0执行且HALT。

独立headed Chrome双profile Cookie/LocalStorage隔离PASS，再用新profile依次DOM演练T01/T02/T03。T01三次Mock模型HTTP：旧list_files显式executed=false跳过，后续带精确source reference、真实read_file读取README，合成两句回复带标识；T02一次、not_applied，刷新不重发；T03一次、cancelled并关闭、不可信部分/Usage不升级。共5次Mock HTTP、三个服务wait exit0，端口/Lease/库一致、profile清理。它们不是任何真实Provider成绩。

SDK/HTTP/来源证据只证明对应层级。原生applied是on_dispatch准入（甚至早于UAT reservation），不能推出远端处理或语义遵从；真正Semantic Adherence仍须未来实际工具顺序与回复独立评审。不因直接答复/时序错过补跑，也不扩大预算。

预注册/冻结源码提交`6337a20ae926f28cae0446f5e008bc754d2e14e0`，唯一prepare、唯一freeze与verify完成；302源文件hash等于权威回归版本，原配置/workspace字节与inode/两库inode及完整性一致，8901可绑定、Lease可用。Acceptance只改文档和脱敏证据，冻结后源码未改。Live仍需新GRANTED_6_REQUESTS和全部当前环境预检，只可T01→T02→T03一次。cost=null，原真实能力未知见remaining-risks。
