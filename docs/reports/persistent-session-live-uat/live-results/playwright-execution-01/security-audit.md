# Security and integrity audit

冻结verify在执行前、各轮/阶段及执行后通过：preregistration祖先关系合法，freeze/prepared、生产源码、pyproject/uv.lock、原Provider文件hash、workspace指纹及两数据库dev/inode保持。没有修复/替换冻结资产，没有prepare/freeze、新账本或依赖修改。授权的事件追加与账本结算不是污染；工作区文件字节未变化。

执行前原账本0 cases/0 reservations；结束3个唯一finished cases、14 returned reservations，每个HTTP尝试1，0未结算、0失败、无halt。SDK隐式重试0；备用构造仍受同一账本限制，实际未启用。没有工具调用、审批、MCP、命令或写文件请求，产品Tool Authority/Receipt/Controller未放宽。操作员自身终端仅在用户授权范围运行临时Playwright和报告工作。

两个SQLite integrity_check=ok，foreign_key_check无错误。事件库100事件、14 completed turns、0 tools、3 sessions、两active/一superseded/一revoked Pin。三服务正常SIGINT退出（exit0），8889关闭，WorkspaceLease正常获取释放，无锁删除、强杀或execution_uncertain。自己的Chrome与probe进程退出、profile删除；私有数据目录0700，数据库0600。

8765本轮没有监听；停止launcher39852及defunct子39853未被操作。既有用户Chrome56352始终保留，未访问其页面、配置、Cookie或聊天。没有人为造成用户内存会话丢失，但无法保证外部已消失的旧服务保存了此前内容。原服务配置workspace与UAT解析路径不同，没有其它进程打开UAT两库。若其它应用共享供应商账号，远端额度/限流仍可能共享；本账本只统计本批次14次，不把别的应用用量混入。

重要诊断瑕疵：prepare verify CLI无论执行状态均硬编码输出real_requests=0。它校验冻结完整性，不是使用量接口。执行后读取原SQLite reservations确认14，与14份observer和供应商Usage一致；未用静态0掩盖或重置账本。源码本轮未修改，建议独立修复。

提交范围仅脱敏新报告、UAT/合成探针截图与AI_HANDOFF。没有私有SQLite、完整模型Prompt、Cookie/CSRF、API Key、Receipt、审批nonce、Chrome Profile、调试数据或用户原聊天。截图仅展示本轮冻结合成任务与其真实回答。旧报告原样保留，用户主checkout未提交修改不触碰。证据SHA索引见evidence-hashes.json。
