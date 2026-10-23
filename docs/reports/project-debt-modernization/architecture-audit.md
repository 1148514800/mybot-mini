# 全项目架构审计

事实基线为远程 codex/web-chat-ui `1de96420122daf0d75a650952613a05d1ace99ac`，已先 fetch/核对。独立分支/worktree开发；原 main 和用户改动保留。审计方法是全生产模块清单、关键调用链逐段阅读、异常/裁剪/预算/资源生命周期检索、Phase文档交叉检查以及基线/专项/全量测试。不是形式化安全证明，也不宣称对所有潜在攻击做了动态复现。

## 组件与调用边界

CLI run_gateway / Web ChatRuntime → GatewayConfig + workspace lease → Registry + MCP owner → AgentLoop → Session/Context/Skills/Plan → ContextManager → optional ContextCompactor → RuntimeAccounting → TracedClient(可选) → ProviderFailoverClient → SDK。工具执行仍由Registry/Controller/审批/工具自己实施权限与发布屏障；观察事件只有只读数据，不参与授权。

| 子系统 | 主要审查位置 | 判定与证据 |
|---|---|---|
| 启动与配置 | main/app/config、GatewayConfig/build_client | 字段优先级、SDK重试、清理与跨进程协调已修；旧配置默认语义保留 |
| ReAct/规划 | agent/loop、planning、CodingTaskController | 请求门、工具批次门、真实执行证据与Plan分离合理；修Web失败结论；不按模型自报verified |
| Context/Session | context/context_manager/session、session_store | 规则视图不改canonical历史合理；新增完整请求估算与可选摘要；存储版本/原子替换保留；共享存储单写者限制未改变 |
| Skills | skills/registry、tools/skill | 元数据/YAML安全加载、路径检查及完整技能内容保留；无新远程代码执行；慢IO风险保留 |
| 基础文件 | tools/file/list_files | 修无界读取后静默裁剪与UTF8计数；简单路径工具TOCTOU仍是后续风险 |
| 仓库检索 | repository/read_file_range/search_code/git_tools | 范围读取、搜索、只读Git的输出与路径边界合理；未放宽Git hooks/filter/外部helper保护 |
| Patch/Receipt | tools/patch、change_journal | Preview不写入；单次scope能力、指纹重验、发布与回滚不确定状态保持；场景C原工具真实执行 |
| 命令/Undo/Git | run_command、command_approval/process/macos_sandbox、git_workflow、undo | 审批、Seatbelt、命令证据、当前Revision验证保留；capsule释放补齐；没有自动yes或修改审批策略 |
| MCP连接与鉴权 | manager/transport/response_limit/credentials/oauth/oauth_callback/approval | 同owner进入退出、绑定目标、重定向/重放限制、OAuth状态/PKCE由SDK承担、回调一次性及超时清理合理；不迁task或关闭安全边界 |
| MCP发现/路由 | discovery/retrieval/relevance/router | 原catalog和schema激活预算保留；ContextManager接口兼容；特殊短名称质量列潜在风险，不重调旧分数 |
| Provider | provider_failover | 暂时性错误白名单、主备独立窗口重验、取消传播、sticky语义；工具不重放；客户端关闭失败保锁 |
| Evaluation | trace/coding_metrics/judge/grader/campaign/live/lifecycle/supervisor | 仅trace加可选runtime数据；全局物理预算仍先于发送；judge/Strict/任务包/raw/旧reports不改 |
| Web服务与前端 | server/runtime/approval/security/static | loopback Host/Origin/cookie/CSRF/SSE边界保持；状态/指标一致、切换异步竞态防护、合作进程锁；内存历史是合理范围限制 |
| 依赖与交付 | pyproject/uv.lock/scripts/check_phase/docs | uv frozen基线可重现；未引入Tokenizer或前端大依赖；追加三套合同测试；不修改Phase Tag/ZIP |

## 保留的合理设计

小项目继续使用现有抽象，不引入第二套Agent框架、长期摘要数据库或新评分层。Session完整历史与一次请求视图分离，Context算法不授予工具能力。Controller只接受当前Revision的原生测试证据；Preview/Receipt/Commit与verified严格分开。Web面向本地单用户，非公网多租户；产品限制不标成Bug。语义摘要用原文引用而非自由生成，取舍是可审计性优先，真实质量仍未知。

全部债项、复现/测试及未修理由见 technical-debt-register.md；历史资产完整性见 security-audit.md。没有把本轮OFFLINE结果推广为真实模型能力提升。
