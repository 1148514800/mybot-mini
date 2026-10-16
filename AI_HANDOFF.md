# AI Handoff

## 当前目标与状态

Phase 13 实现与开发验证完成，等待当前提交的独立归档/还原验证；不要进入 Phase 14。Phase 1–12 旧 Tag/ZIP 不变。保留用户未提交的 mybot/app.py 三处注释与 workspace/instructions/USER.md 修改，不 Push、不调用真实 LLM API。

## 已完成与架构

- HTTP配置增加严格 none/bearer_env；stdio拒绝auth，MCP明文凭证/任意Header字段拒绝。credentials.py从显式环境引用读取连接时快照，RFC b64token、4096 ASCII字节上限，缺失/非法分别credential_missing/credential_invalid；repr不含Token。
- transport.py先校验固定Endpoint/禁止GET恢复，再清除身份Header，最后注入可信凭证；POST/首次GET/DELETE一致，identity请求、trust_env=False、默认TLS证书校验、禁代理/netrc/重定向/重试保持。401/403全部方法安全分类。
- response_limit.py包装原始AsyncHTTPTransport响应流，非SSE实际字节在交给httpx解码/SDK缓冲前限2MiB，忽略Content-Length，超限块不交付、立即关闭流。非identity编码读取前拒绝，SSE继续SDK默认1MiB单事件限制。errors.py共享安全类型，transport保留导入兼容。
- Demo增加--require-token-env，hmac.compare_digest，缺失/错误认证统一401且不回显；保留本机内存五工具和Host/Origin防护。
- 复用Manager/Adapter/Approval/AgentLoop/Session/Planning；未改这些模块。MCP/mcp-types仍2.3.0，httpx2仍2.13.1，依赖不变。

## 修改文件

新增mybot/mcp_client/{credentials,errors,response_limit}.py、scripts/check_mcp_auth.py、docs/phases/phase-13.md。修改mcp_client/{config,transport}.py、HTTP Demo、check_phase.py、config模板、README、阶段索引和本交接。

## 验证结果

38项Phase13专项通过（32项HTTP认证/权限集成、6项接收流测试）。全量Phase1–13共222项unittest及Phase1/2断言通过；Phase12原28项真实HTTP回归也独立通过。增强故障响应使正文含合成Token后的401/403定向2项通过；超大SSE使用合法JSON-RPC结果，定向验证通过。编译通过（先只清理文件头确认的AppleDouble ._*）。归档安全集成检查通过，归档/还原最终结果随后更新。

测试覆盖实际SDK初始化/list/call、认证POST/GET/DELETE与快照、双Server凭证隔离、无配置/错误/缺失凭证、字段/Header安全、权限真实副作用、代理/netrc和DEBUG/审计/Schema/模型请求/持久化Session不注入Token、401/403/重定向不重试、超限启动/发现原子清理、字节边界/未知长度chunked/伪造长度/压缩拒绝、SSE正常及超大单事件、取消和Client释放、混合传输/前序stdio进程退出。伪造长度在底层合成Transport注入，真实HTTP framing无法合法传递虚报的小长度。无公网/第三方MCP/真实LLM调用。

## 已知限制与安全

静态Bearer不是OAuth，无刷新/轮换/Vault；目标和受众由用户预先确认。明文loopback只用于合成Token教学，实际生产凭证使用可信HTTPS。未连接公网TLS服务器。拒绝压缩响应，非SSE2MiB限制不是完整网络DoS/总内存沙箱；SSE无总流量上限。认证不授予工具权限，TLS不代表服务端行为可信，Server能保存收到数据，Session仍可能保存用户工具参数；超时/取消/输入超限可能已有远端副作用，无重试/回滚。日志抑制仍为Phase12进程级单Gateway约束。

## 下一步与不要重复

完成本阶段提交后，从干净APFS独立worktree运行save_phase.sh 13，发布同级ZIP并执行restore_phase.sh 13及冻结安装/编译/全量回归；更新本快照记录确切Tag/Commit/路径。不要改用户修改、旧归档或真实配置/历史；不要覆盖已存在Tag/ZIP，不进入Phase14。学习资料仅见docs/phases/phase-13.md，历史通过Git查询。
