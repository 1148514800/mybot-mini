# 技术债登记

审计口径：已确认缺陷、已知限制、可能风险、维护债分别统计；未复现的风险不冒充漏洞。确认缺陷 P0=0、P1=9、P2=2，均已修复。另有2项能力限制改善、8项剩余事项。全部项目子系统的合理设计见 architecture-audit.md。实现提交见验收报告。

| ID | 级别 | 性质 | 状态 | 位置 | 问题与触发 | 测试证据 / 未修复原因 |
|---|---|---|---|---|---|---|
|D01|P1|已确认缺陷|已修复|config.build_client|单供应商 SDK 默认重试可在逻辑请求计数外重复发送；构造客户端检查 max_retries。|check_token_budget.test_single_provider_sdk_retries_disabled；Accounting MockTransport；统一设0|
|D02|P1|已确认缺陷|已修复|provider_failover.ProviderFailoverClient.create|默认捕获所有 APIError，401/403/422 等配置或权限错误也切备。|test_transient_only_default_failover；只允许连接/超时/429/指定5xx，原 Harness 自定义策略保留|
|D03|P1|已确认缺陷|已修复|agent.loop / web.runtime / evaluation.trace|各入口逻辑、物理、Usage 缺失口径不统一；失败与无Usage合成响应复现。|Accounting missing/mixed/failover/trace 测试；共享 RuntimeAccounting，旧评分输出不改|
|D04|P1|已确认缺陷|已修复|workspace_lease / app.run_gateway / web.runtime._run|不同 CLI/Web 进程原可同时写同一目录，原 lease 仅单 Runtime。|新 process collision/crash release/Web busy/uncertain/CLI close failure 测试；flock 合作锁|
|D05|P1|已确认缺陷|已修复|config._llm_value|存在 llm 对象时 provider 级参数 fallback 被整个对象的 truthiness 屏蔽。|test_provider_level_option_fallback；按字段优先级继承|
|D06|P1|已确认缺陷|已修复|tools.file.ReadFileTool.execute|先全文件读取再静默截50000字符，可能无界读取且误导完整性。|test_basic_file_bounded_read_and_utf8_write；限量读取及明确裁剪标记；场景B|
|D07|P2|已确认缺陷|已修复|tools.file.WriteFileTool.execute|中文成功消息把字符数写成 bytes。|同上：中文两字返回6 bytes|
|D08|P1|已确认缺陷|已修复|agent.loop._finish_turn / web.runtime._run|非Coding失败/未完成Plan有机会在 Web 结束时显示完成。|test_failed_plan_web_is_not_completed；状态取真实结束原因|
|D09|P1|已确认缺陷|已修复|agent.loop.run|CLI 原样打印 SDK异常内容可能含响应载荷或凭证。|test_cli_does_not_echo_sdk_error_secret；只输出异常类型与通用错误，保留资源快照|
|D10|P1|已确认缺陷|已修复|app.run_gateway finally|CLI 未显式关闭最后一轮 Git capsule；新增租约还必须等待所有清理确认。|capsule.close 路径检查；CLI close failure 保锁；原 repository 适配器回归|
|D11|P2|已确认缺陷|已修复|web/static/app.js select|快速切换会话时旧 refresh 返回后可能创建错误会话 SSE。|在 await refresh 后复核 selected===id；原Web隔离回归；竞态依据代码时序，不宣称浏览器压力测试|
|D12|P1|已知限制|已改善|agent.context_manager.count / token_counter|字符预算不能代表Token窗口，旧逻辑本身符合max_chars合同。|新增estimate预算和完整请求计量，strict无可信映射拒绝；16项Token测试|
|D13|P1|已知限制|已改善|agent.context_manager.summary / context_compactor|规则摘录可能丢失跨轮目标与约束，不能称旧算法错误。|新增显式opt-in引用式语义选择，22项压缩测试；默认规则算法保留|
|D14|P1|已知限制|未修复|token_counter.TokenCounter / gateway deployment|官方Tokenizer资源存在，但coco/coco2实际部署映射不可验证；精确计数不可用。|无真实请求授权；须供应商版本与模板证据及后续独立授权对照，strict失败关闭|
|D15|P1|可能风险|未修复|tools.file.FileTool._resolve / WriteFileTool.execute|resolve检查和后续open/write之间的外部路径替换存在TOCTOU窗口。|源码风险；本轮未构造利用，不列已确认漏洞。Coding使用原硬化Repository/Patch；遗留简单工具需后续descriptor相对IO|
|D16|P1|已知限制|未修复|storage.session_store.SessionStore.save|原文声明不支持并发写；不同workspace若配置同一session.path仍可能最后写覆盖。|本轮工作区锁不覆盖共享Session路径；保持单写者约束，后续增加存储路径锁/版本冲突检测，不擅改格式|
|D17|P2|已知限制|未修复|web.runtime.ChatRuntime / Conversation|Web重启丢历史、20会话/64展示消息/128事件上限。|现有产品范围，非Bug；持久化需能力脱敏和恢复协议单独设计|
|D18|P1|已知限制|未修复|agent.context_compactor.ContextCompactor|合成测试无法证明真实模型引用选择质量或成本收益；工具成功文本也非当前验证。|继续低信任/原生Controller判断；需单独授权实际日常验证|
|D19|P2|可能风险|未修复|tools.file / skills.registry / storage.session_store|部分磁盘IO同步，慢磁盘可延迟事件循环取消。|静态风险，未做慢设备实验；新read_file有界但不能保证硬实时；后续线程化需取消与写屏障设计|
|D20|P2|可能风险|未修复|mcp_client.relevance / retrieval tool-name handling|部分检索逻辑按 __ 分割短名称，特殊远端名称可能降低匹配质量。|非授权碰撞结论；不重调冻结路由基准；新增专门案例后再判断|
|D21|P2|维护债|未修复|agent.context_compactor → web.security.redact|复用原脱敏函数形成Agent对Web安全模块的方向依赖。|无新依赖/副作用；后续可迁共享安全模块，需保持所有历史脱敏合同|
