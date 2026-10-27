# 安全与权限审计

本轮只有离线授权，真实DeepSeek/GLM/摘要/Judge请求均0。新精确GRANTED_2_REQUESTS之前，入口拒绝旧1/6/8请求授权和NOT_GRANTED，早于配置/SDK/批次访问。Mock固定httpx.MockTransport+AsyncOpenAI，合成地址mock.invalid，不使用远端Provider；prepare只读现有配置字节、模型匹配和凭证存在性，不验证远端有效性。

新工具仅存在scripts层，未注册为Agent工具；未修改生产AgentLoop、ProviderFailover、Streaming解析器、SteerInbox、Tool Authority、TaskContract、Decision Provenance、Pin、EventStore、RuntimeAccounting、Cookie/CSRF/CSP/Origin或权限。空Registry，MCP/Skills/Coding关闭，不恢复审批、Receipt或执行权限。原已执行工具不被伪记未执行、未完整工具不执行、配对/终态/旧CLI/非流式规则由原专项回归验证。

端口只127.0.0.1，单bind持有socket，无REUSEPORT、随机Live换端口、未知进程信号、系统参数改动或删锁。外部占用和自身未退出Listener均拒绝；应用ready、Listener归属和最终exit0分别核对。自己的launcher/服务身份在信号前验证，启动失败不创建Attempt，HALT不阻止自己资源清理。

浏览器为新的0700 Profile，不读复制用户Cookie/LocalStorage；双profile同Origin双向隔离。异常清理先Context后driver，最后确认自己Chrome退出及目录dev/inode/UID/父级/非symlink才删除。关闭/删除失败如实记错误与不确定性，不以事后目录消失掩盖失败。用户Chrome、8765服务与旧工作区不操作。

旧T01/T02/T03报告、旧3/6/3011 Token、原冻结源码与旧私库/HALT原样保留。开发分支只新增UAT/操作员模块、测试及新报告、当前交接/专题索引，不修改历史报告、main、Tag、ZIP、生产依赖或配置。共享Git对象库AppleDouble旁索引不处理；仅捕获已知警告，保留返回码和远程HEAD证据。

公开文件只含计数/固定分类/有界结构/来源ID/hash和审阅过的脱敏截图。私有配置、SQLite、Chrome Profile、完整模型请求/回复/chunk、工具参数、Cookie/CSRF/nonce及原始私有异常日志不提交。提交前对全部已跟踪文件与新报告进行真实凭证值扫描、禁入资产检查、JSON/证据hash校验、diff审阅。具体机器可验证结果见offline-validation.json、freeze-evidence.json与delivery-validation.json。
