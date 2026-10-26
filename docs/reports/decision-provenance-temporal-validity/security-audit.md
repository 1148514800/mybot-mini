# Security audit

PASS。逐项路径和辅助凭证扫描结果见security-evidence.json。原Pin写入口、TaskContract、ContextCompactor、TokenCounter、Tool注册/执行模块、Web security/approval、生产依赖与锁文件保持字节一致；只有Web控制命令拒绝列表增加/decisions。没有改变Cookie、CSRF、Host、Origin或CSP策略。

新决定视图只从真实Session范围的消息和Pin事件读取；模型无确认工具。分类提议没有事件写入、审批或权限。SQLite v2提交索引与原事件在同一事务写入，损坏索引、未来/内部历史边界拒绝；既有存储完整性、热日志恢复、私有权限、幂等、并发和预算检查保留。未新增恢复旧执行权威的字段。

凭证辅助扫描和人工内容复核覆盖本轮变更；跟踪路径检查未发现真实config/config.json、.env、私有SQLite、Chrome profile、Cookie或调试数据。截图只含公开合成设计语句，未打开设置或旧8765页面；不存在聊天、API Key、CSRF、Receipt或审批nonce导出。完整合成请求日志留在临时目录，不提交。

浏览器动态隔离通过，真实消息和Pin操作均经页面，未用写API替代。两次自身合成服务正常退出、端口释放、Lease重新获取成功，Chrome配置文件清理。未向旧服务发请求、关闭或重启用户Chrome；不据此对外部独立进程的自然变化作额外保证。

真实DeepSeek/GLM/摘要/Judge/Provider HTTP均0；离线failover测试日志中的模型名和切换提示来自Fake/MockTransport，并非付费请求。原1682基线之外的28项Source-Aware UAT离线预算测试仍单独执行，未连接原Live批次。旧Live报告、冻结脚本/Fixture、账本、Tag/ZIP未改。

初次完整回归期间操作员继续编辑本轮源码，原离线批次冻结门如实拒绝frozen_environment_changed；该次不是有效最终回归，也未请求真实模型。修正呈现后冻结本轮源码再完整重跑，最终结果单独记录，未修改门或删除旧断言来制造通过。
