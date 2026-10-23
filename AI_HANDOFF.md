# AI_HANDOFF

## 当前目标与状态

全项目技术债审计、Token/Context现代化完成离线验收：OFFLINE PASS。基线远程 `codex/web-chat-ui` 的 `1de96420122daf0d75a650952613a05d1ace99ac`；独立分支 `codex/project-debt-modernization`。按Implementation、Acceptance两个提交交付；本任务不属于新Phase，不合并main，不创建Tag/ZIP。

Implementation：`b0346bdfca3451101c8af65be7beeaf2c17baaa6`；Acceptance为本快照所属报告提交。

## 已实现与架构决策

TokenCounter对真正可见请求区分JSON字符/UTF8字节/保守估算/供应商Usage/unknown。保留legacy_chars与旧max_chars语义；estimate显式限额+输出预留+主备窗口分别重验；没有已验证网关Tokenizer映射，strict拒绝未验证请求，不用GPT编码替代。费用未知。

ContextCompactor默认关闭：semantic需allow_extra_requests=true，选取九字段来源原文引用，低信任assistant参考；不恢复授权/Receipt/Plan完成/当前Revision测试证据，不改原Session。输入/输出/次数/超时/取消受限，复用Controller与Evaluation预算；短期缓存仅同次handle_message完全相同历史可复用。

RuntimeAccounting统一CLI/Web/Trace的logical、physical、HTTP尝试、Usage、压缩与裁剪状态；缺失不补零，最后实际备用请求策略可观察。Trace只加观察属性，不改冻结评分。额外修复11项确认缺陷：SDK隐式重试、非暂时错误切备、指标口径、跨进程锁、配置继承、读取静默裁剪、UTF8字节数、Web失败状态、CLI异常载荷、capsule清理和会话切换竞态。

CLI/Web合作式flock按规范化工作区路径隔离：CLI整个会话持锁，Web每任务清理后释放；不确定清理保锁至进程退出，不删除未知锁。仅协调合作入口，不隔离外部编辑器/恶意同UID进程/不同workspace共用Session路径。

修改集中在agent Context/Loop、config/provider、runtime_accounting/workspace_lease、app、基础file工具、Web观察、evaluation/trace；三套新增专项及check_phase追加。用户说明README、docs/context.md、docs/web-ui.md、config/config.example.json；审计报告在 docs/reports/project-debt-modernization/。

## 验证与保护

基线1293/1293、35套件；最终1354/1354、38套件、零跳过，新增61项（Token16、Compaction22、Accounting23）。7组必需重点专项、repository34、autonomy100分别通过；compileall/diff检查通过。真实AgentLoop合成A长对话、B长工具、C搜索→读取→Preview→Receipt→原生测试，C只称指定范围verified，不称Strict Success。

真实浏览器HTTP/SSE验证新指标，截图随Acceptance报告；合成Usage300与输入估算5067分别显示，窗口unknown。真实模型API0，实际人工TTY/浏览器审批0；自动测试中的既有合成审批回调不计人工批准。不得使用旧A/B剩余额度。

1560个保护文件哈希未变；main与Tag不变，历史Phase文档/报告/raw/ZIP、原工作区mybot/app.py与workspace/instructions/USER.md的用户修改保留。旧1293项断言没有删改；Controller、Patch发布器、审批、Strict评分未放宽。原Git对象目录的ExFAT AppleDouble索引警告未通过改历史文件“修复”。

## 已知问题与下一步

剩余P1：实际网关Tokenizer/template/window映射未验证；legacy基础文件工具TOCTOU潜在风险；跨workspace共用Session路径仍只支持单写者；真实语义质量与供应商费用/可靠性未验证。P2：Web内存历史限制、慢IO取消风险、特殊MCP短名称检索风险、Agent复用web.security脱敏的层次依赖。详见remaining-debt与readiness。

下一步是在另行授权下进行受控真实日常验证，先保持独占工作区/独立Session路径；semantic生产启用会增加费用。不能宣称全项目全部READY。不要重复历史Benchmark、移动Tag/覆盖ZIP、迁移Session格式或把摘要当当前文件事实。CLI/Web修改配置后重启；原字符/规则模式仍可继续使用。
