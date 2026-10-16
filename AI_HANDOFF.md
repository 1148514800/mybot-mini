# AI Handoff

## 当前目标与状态

Phase 14已完成、提交、独立归档与还原验证。annotated phase-14指向748e6c127cca87e05877f119be5685a01c879b9d；ZIP：../mybot-mini-snapshots/phase-14.zip（117条目）；学习还原：../mybot-mini-learning/phase-14。不进入Phase15。Phase13已在此前用户授权后Push，Phase14默认仅本地。保留用户mybot/app.py三处注释与workspace/instructions/USER.md未提交修改，不改真实config/Session，不访问真实LLM或第三方OAuth Provider。旧Phase1–13 Tag/ZIP不变。

## 实现与架构

- credentials.validate_auth分派oauth_pkce到oauth_config.py；严格Issuer/Client/Scope/固定127.0.0.1 Callback，拒绝凭证和未知字段、stdio auth；none/bearer兼容。
- oauth.py：MemoryTokenStorage预置issuer绑定公共Client，内存Token验证/引用释放；GuardedOAuth组合官方OAuthClientProvider.async_auth_flow，不自写PKCE/state/iss/兑换/刷新。OAuthBoundary分别白名单资源、PRM/AS发现及验证后同Issuer Origin端点；资源精确匹配，发现不带凭证。授权/兑换/刷新均检查resource，Scope须符合本地集合，不注册/不扩大。
- 初始initialize仅允许一次401认证与一次重发；工具401/403在response hook到达SDK前失败，阻断重新授权/Step-Up/重放。失效Token先由SDK刷新；刷新失败/Scope扩大/无Refresh Token安全失败，不发送匿名工具。仅storage验收的当前Token可上网，防止SDK先赋context再验证的副作用。
- SDK OAuth锁跨越响应等待，SDK退出先DELETE再取消POST；仅锁占用时的清理DELETE使用当前有效已验收快照直接发送一次，避免取消被拖至超时；不改Manager/owner Task，不自写刷新协议。
- oauth_callback.py：先绑定再CLI确认/browser，单次结构化回调，SDK验证state/iss；重复/非法参数、路径/Host/编码/大小拒绝。120秒等待，监听关闭先取消处理Task再wait_closed（Python3.12）；安全页面无敏感值。
- Phase13 ResponseLimitTransport不改，继续保护OAuth元数据/Token；拒绝它们伪装SSE及压缩，合法MCP SSE仍用SDK事件限制。SDK敏感异常统一安全类别，进程级quiet日志机制延续。
- Demo为两个本机HTTP服务，预注册公共Client、显式同意、S256、Code一次性、受众/Scope/过期、Refresh轮换；内存五工具不写私人文件。Uvicorn显式ASGI3以正确处理绑定方法。

## 修改文件

新增mcp_client/{oauth,oauth_config,oauth_callback}.py、scripts/{mcp_oauth_demo_server,check_mcp_oauth}.py、config/mcp.oauth.example.json、docs/phases/phase-14.md；修改credentials.py、transport.py、check_phase.py、README、阶段索引和本交接。Manager/Adapter/Approval/AgentLoop/Session/Planning/ResponseLimitTransport及依赖锁文件未改，MCP仍2.3.0。

## 验证

52项专项（48 HTTP/SDK/Agent、4 Callback）通过。实际本地HTTP+官方Provider完成授权/刷新，浏览器仅替换UI入口，用HTTP真实同意/Callback；没有固定Provider返回值。state/iss/S256/Code复用/错误verifier/Resource受众、刷新轮换旧值失效、工具副作用后401/403仅发一次、审批真实状态、Plan/配对/clear、隐私、两Server隔离、三传输共存、接收限制/SSE/取消/内存释放/CLI均验证。Phase1–14全量274项unittest及Phase1/2原断言通过，mybot与scripts编译通过，归档安全集成检查通过。干净APFS独立worktree运行save_phase.sh 14成功，ZIP独立冻结安装/编译/274项回归及Phase1/2断言通过；从实际同级学习目录restore_phase.sh 14还原后再次uv sync --frozen、mybot/scripts编译及全部回归通过。还原目录仅清理文件头确认的118个AppleDouble元数据文件，ZIP无._*。ZIP Commit注释与Tag一致，SHA256：51eb5964e013c8f4d8dc8aa4aaf74ebda9170c5e3a8c0727e87f9d4e2d56c861。旧13个Tag对象和全部旧ZIP SHA256均验证不变；临时worktree已移除。

## 限制

预注册公共Client/内存Token；无动态注册/CIMD/Client Credentials/跨重启恢复/撤销/Secret Vault。严格同Issuer Origin、固定发现和精确resource拒绝部分合法跨域部署；SDK选Scope与本地集合不符就失败，包括自动offline_access。要求正expires_in；无公网TLS实测。回调仅当前macOS循环验证。SDK敏感Token/context对象不能打印；项目对象repr不含秘密、认证不注入模型/Session，但用户自行提供或Server反射的正文仍可能含秘密。TLS/OAuth不代表服务端行为可信；超时/认证失败可能已有副作用；失效凭证时清理DELETE不保证服务端Session删除。进程级日志抑制仍只支持当前单Gateway模式。Demo非生产身份服务。

## 下一步与不要重复

Phase14结束，等待用户下一项任务；不重复创建phase-14或覆盖ZIP，不改旧归档，不混入用户app.py/USER.md修改，不Push、不进入Phase15。学习见docs/phases/phase-14.md，历史通过Git查询。
