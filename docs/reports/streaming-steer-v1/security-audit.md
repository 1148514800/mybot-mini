# Security audit

保护路径及凭证辅助检查见security-evidence.json。旧Live/Decision报告、UAT冻结脚本与Fixture、Pin、Decision Provenance、Context Projection、TaskContract、Controller、TokenCounter、工具注册及权限/Receipt模块保持字节一致。仅原AgentLoop、Provider/Accounting、事件类型和Web增加接入点；没有重写成熟循环或执行新权限。

Web Boundary的Cookie、Origin、CSRF、Host与CSP策略不变。Steer新增路径仍通过同一中间件，检查真实Session/Turn所有权和运行状态；模型无确认/Steer工具。旧/跨Session/空闲请求、重复不同内容、容量超限、审批等待和敏感输入拒绝。没有自动批准命令或MCP；浏览器F明确拒绝合成命令，持久工具effect=none。

流式工具参数不进SSE，必须完成可信终态组装后交由原执行门。模型缺失finish不能走旧legacy工具兼容成功路径；断流、取消、格式错误均不执行部分调用。Steer取消结果明确success=false/executed=false且配对，已执行工具不重标或回滚。

增量先跨Chunk缓冲再脱敏，专门验证API Key三段、Receipt/nonce多段、长行抑制及多行已知凭证禁预览；SDK原始异常不发布。预览和审计均有硬上限，无每Token持久化、无每Token完整GET、无无界队列。关闭超时/失败保留原不确定阻止与Lease，取消不重放。

新增Steer事件采用v2，旧事件与DB v2表结构不改；未打开用户或历史Live库，只在独立临时库测试。重启不恢复待应用Inbox、旧Stream、审批、Receipt或verified。不同版本写者的升级需协调，不共享活动库。

最终Chrome使用独立0700身份并完成双向隔离探针。只对本轮新建服务执行SIGINT/等待退出/Lease复核，清理自己的profile；未访问8765、用户Chrome或旧会话。未提交Cookie、CSRF、nonce、Receipt、原SQLite/profile、原始SDK日志或完整模型Prompt；截图仅有公开合成内容，另附SHA。

全仓跟踪路径与文本辅助扫描，加本轮源码/报告/截图人工复核未发现真实凭证。生产pyproject.toml/uv.lock未变，Playwright仅可选独立环境。真实DeepSeek、GLM、摘要、Judge和Provider HTTP均0；离线日志中的Provider切换来自Synthetic/MockTransport。历史Tag/ZIP和所有旧断言保持。

首次完整回归已通过；其后补严运行中计数快照、stale/rejected响应、请求阶段字段及严格JSON组装，进行了针对性、浏览器和完整复验。重复执行不重复计入测试总数，不以首次版本替代最终源码结果。
