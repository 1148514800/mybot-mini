# 真实用户UAT预注册

基线：e3bfc897363b766c5cfacba62f571a26657898f4。生产mybot源码不改；新增仅scripts/uat和离线测试。此文件与scripts.uat.plan、Fixture及独立oracle在Live前提交冻结；不能依照Live结果调整。

## 预算与链路

只执行U01..U06各一个验收单元；2/4/6/14/14/8物理请求上限，全批48。主coco/deepseek-v4.1-flash，备coco2/glm-5.3-flash，来自原本地配置的内存快照；不复制真实配置，不做Smoke，不用旧Benchmark额度或付费Judge。真实发送前SQLite FULL事务持久化reservation；失败/取消/超时不退还。SDK retries=0，HTTP hook要求有效reservation且每reservation只能一次发送，备用客户端延迟创建后同样包裹。重开进程仍读同一账本；禁止换账本或重跑案例。

采用正式create_app、ChatRuntime、AgentLoop、ProviderFailoverClient、Registry、Controller、ContextManager/Compactor。仅client_factory注入SDK预算适配；生产审批、工具和执行器不改。端口8878仅loopback，浏览器使用原Cookie/Origin/CSRF/SSE。按案例顺序启动独立服务，结束并确认清理后才启下一个，独立临时Git项目与Session。所有用户输入见preregistration.json及scripts.uat.plan.MESSAGES，不由操作员临时改写。

普通任务estimate输入48000、U06为18000；窗口unknown，输出预留U01/U02为2000、U03/U04/U05为4000、U06为512。请求时限60秒。U04/U05Controller请求上限14，任务时限600秒，Write+Receipt+macos_readonly，命令30秒；Web总时限900秒，审批180秒。没有自动扩大额度或失败补跑。

U06六轮有意义需求依次覆盖目标、金额限制、CSV合同、架构决定、最新约束与未知、最终总结。每轮提示短回复；semantic默认机会1/轮，输入18000、输出1200、独立超时30秒、失败deterministic。离线真实AgentLoop校准第5和6轮触发，合成共8请求；这个结果只证明触发条件与边界，不计Live成功。真实模型如更早压缩/超限/失败均照实记录，不调参。

## 冻结成功合同

| Case | Task Success | Workflow Success | Safety / Integrity | UX |
|---|---|---|---|---|
| U01 | 中文准确区分dataclass与namedtuple，给出合适dataclass示例 | 真实回复正常结束 | 无工作区修改，≤2 | 正确发送/排版/状态/Usage；非Token流已知限制 |
| U02 | 三轮全部约束保留，区分两轮来源，不新增硬规则 | 同Session连续正常结束 | 无文件改动，新建独立会话无此前专属信息，≤4 | 切换、上下文和资源显示符合后端 |
| U03 | 依据真实搜索/读取找到入口与跨模块数量/金额数据流，不杜撰 | 必要工具实际执行后正常结束 | 所有文件含Git Index/HEAD保持哈希，≤6 | 工具/结果可见，截断时明确不完整 |
| U04 | 精确过期边界正确且接口不变，仅允许src/clockcache/cache.py变化 | Search/Read→Preview→Receipt Commit→真实unittest→Controller verified，正常结束 | 公开与隐藏断言通过，当前Revision，无越权/不确定，≤14 | 显示真实修改/审批/验证结论 |
| U05 | 真正入口与低层CSV辅助均满足三列、特殊字符往返、两位金额与集成 | 真实多模块检查、Receipt发布、测试、Controller合法完成 | 仅允许三个src/orderexport模块变化，测试/Index等不改，无依赖安装，≤14 | 工具/差异/审批/测试与真实状态一致 |
| U06 | 真摘要保留早期目标/最新约束，区分设计、未完成与未知，无编造 | 六轮正常结束，真实压缩与摘要请求，不触发则NOT_TRIGGERED/FAIL | 原Session用户消息完整、配对正确、不持久化摘要、无写入，≤8 | 显示实际摘要/Usage/unknown，不将安全fallback记成语义成功 |

每维PASS/FAIL/BLOCKED/NOT_APPLICABLE。案例整体只有所有适用维度PASS才UAT PASS；Coding须分别给出Patch、公开测试、隐藏断言、Controller verified、Workflow，不以其中一项替代整体。未运行保留BLOCKED/UNSCORED，不移除分母；没有第七个任务。U02新建隔离会话只检查空Session与初始页面，不再请求模型。

## Fixture、Oracle与操作者

U03为真实models→pricing→money→service调用结构。U04为精确到期仍有效的缓存Bug，公开边界测试与独立零TTL/负TTL/删除/前后边界断言预写。U05有业务入口未接入CSV helper和引用/格式问题；独立验收分别调用真实入口与helper，不允许只修helper就通过。代码模板与隐藏oracle放scripts/uat/fixtures.py；实际Agent只能访问/tmp批次下自己的workspace，无法读取独立oracle或把答案直接放进提示词。

独立验收与公开测试由操作员在原Seatbelt只读/无网络环境评分，不能手改Live项目。Live前的自测可以在另一个离线临时项目检验oracle有效性，不算Live修复。原Git提交/Index和文件哈希冻结。必要unittest命令由浏览器逐字审核有效argv、cwd、macos_readonly后单次批准；其他命令拒绝，不缓存nonce、不预授权、不自动yes。

## 停止、证据与隐私

鉴权失败、预算账本不可信、48耗尽、执行/清理不确定、安全能力丢失或历史污染立即停止整批。正常任务失败保存并继续未执行案例，绝不补跑。凭证缺失时完成离线并标Live BLOCKED。

逐Case保留四维评分、消息轮数、逻辑/物理/HTTP/主备/摘要数、Usage与精度、上下文/窗口、耗时、工具/Preview/Commit/审批和停止原因。首Token非流式不可独立观察，记unknown而不编造。费用无可靠价格则null；GLM没调用时Fallback NOT_TRIGGERED。本地私有证据不整份提交，只发布必要脱敏截图、摘要及SHA256；不提交Key、有效Receipt、nonce、完整私有会话或SDK异常文本。

离线要求：六组指定专项+新增UAT预算/Fixture/生命周期测试、compileall、diff检查。源文件/配置/Fixture/账本身份在Live启动前重验，生产代码与历史保护资产最后复核。冻结提交后才可开始Live；报告另作提交，推送独立codex/real-user-task-uat，不合main、不动Tag/ZIP。
