# Tool Authority & Task Contract 验收

**OFFLINE PASS / BROWSER PASS（合成验收）**。指定基线 fd913d938e4bfcda8a6b892780fa987a62906487，独立分支 codex/tool-authority-task-contract。真实API授权与实际请求均0；DeepSeek、GLM、真实语义摘要、付费Judge均0。不合main，不改旧Live结论、Fixture/Judge、Phase Tag或ZIP。

## 交付结论

|问题|事实与边界|
|---|---|
|原来有多少修改入口？|按Agent可达原语分5类：直接文件写、Patch、命令、MCP、宿主Undo；CLI/Web是通道，Skills/只读Git不是额外写原语。另有4类宿主附属写入，详见审计|
|哪些统一？|原生工具与MCP注册能力、Schema和Registry.execute共用门；Catalog再次激活不能恢复被拒权限。文件写默认关闭、原生Patch显式授权|
|哪些仍独立？|命令与MCP保留独立审批/执行域；Undo保留宿主专用协议。不能声称Shell/MCP所有写入受Patch保护|
|普通聊天默认只读？|是，指新安装原生模型文件权限；默认read_file/list_files，无write_file。宿主初始化/历史/锁不因此成为OS只读，显式MCP仍有独立副作用|
|legacy只能显式开启？|是，file_access=legacy_confirm、patch_mode=off、可用Provider及逐次完整审批；无批准/不可展示拒绝，不能与Native Patch并存|
|Patch/Receipt是否保持？|原实现逐字节一致，SHA、dir-fd、元数据、单次Receipt、Preview/Commit、发布/取消/不确定语义保留；兼容写复用其内部检查|
|合同如何证明来源？|当前真实用户精确原文；或真实原生文件读取的有界节选与SHA版本，记录/后续再校验。模型建议/未决分开，不能靠工具参数伪造用户消息|
|测试通过与需求正确？|Controller继续判当前Revision指定测试；合同Level2仅关联真实测试记录，覆盖仍未知；可信独立宿主需求断言才可Level3|
|没有独立验收？|coverage=unknown；Task Correctness始终unknown，因为即使已登记条目全有证据，也无法证明模型提取了所有要求|
|减少错误成功声明了吗？|合成验证了界面不会把公开测试通过升级为全部需求PASS；未测量真实模型错误声明率，不宣称Live质量提升|
|增加模型调用吗？|无固定抽取/评价/常驻Judge请求，无无界续跑；record工具可能消耗往返和Token，A/B预定脚本各6请求，仍受原预算|
|剩余限制？|需求提取可能遗漏或误分类；Level2关联是模型提议；无生产Oracle；无跨轮需求替代；空文件覆盖不支持；legacy/host_confirm无OS隔离，Patch不解决全部并发或跨文件崩溃原子性|

## 验证

最终 `uv run python -m scripts.check_phase`：**44组1448项全部通过，无跳过**。原独立UAT离线补充7组79项全部通过，去重 **1527项**，保留原1469项，新增三组专项 **58项（权限20、合同22、证据16）**。

用户指定的Web53、Preview Receipt53、Coding Reliability42、Coding Failover50、Command Execution62项另行逐套通过；这些260项已在check_phase中，不重复累计。compileall、JavaScript语法、git diff --check通过。实际命令、耗时、日志SHA及去重口径见 [offline-validation.json](offline-validation.json)。

回归真实捕获了旧隐式写入/固定Schema预期、Controller提示末尾JSON解析依赖和资源统计UTF8写入用例。采用显式兼容配置/可关闭合同及提示顺序修复；保留全部原断言，最终重新跑完整入口。详见 [兼容报告](compatibility-report.md)，未删除测试制造PASS。

## 三组合成任务与浏览器

真实AgentLoop、原生工具、SyntheticClient：

- A：调查service/core入口、用户原文合同、Preview不写、单次Receipt Commit、真实unittest1项、Revision1 verified；需求记录为Level2，Task Correctness unknown。
- B：跨模块倍数入口的公开测试1项真实通过，Revision1 verified；缺失输入返回空列表的另一要求未覆盖。独立操作员断言真实FAIL，不进入Agent证据；合同保留该要求为未验证，整体覆盖unknown，未宣称全部正确。
- C：普通聊天不可见write_file，伪造调用被真正执行门拒绝；1次合成请求后停止，无补救模型请求。正常宿主初始化先于基线采集，CLI/Web文件和Git工作树均保持不变。

可重现：`uv run python -m scripts.accept_tool_authority_contract --output /tmp/mybot-contract-synthetic.json`。已交付实际结果 [synthetic-e2e.json](synthetic-e2e.json)。这些任务是机制验收，不是新的质量Benchmark，也不重跑旧T01/T02/T03。

真实浏览器在临时loopback合成服务完成A/B/C，使用真实Web单次命令审批，核对折叠面板、来源简述、当前Revision、缺少独立验收和C拒绝/1请求；最终服务关闭。截图：[A](browser-A.png)、[B](browser-B.png)、[C](browser-C.png)。未使用真实模型SDK或供应商Usage，界面Token未知符合事实。

## 完整性与Git交付

729个既有保护资产无变更；10个关键安全/Controller文件与基线逐字节相同；原有测试断言在披露的显式权限配置迁移后AST一致。全部拟交付文件无私有凭证匹配、禁入路径或不必要大文件。新报告无主机绝对路径、原始私有Prompt、Receipt或审批nonce。用户main两处未提交修改保留。详见 [安全审计](security-audit.md)。

Implementation：`f7d036cac0286f6bda329f2e52f84f9c70b35dc1`。本报告所属后续docs提交为Acceptance；具体SHA通过本文件Git历史获取。交付按用户授权仅Push本专题分支，并在最终答复核对远程HEAD；本报告不预先虚构远程SHA。没有创建新的编号Phase/Tag/ZIP。

学习与架构：[对照](architecture-comparison.md)、[写入口审计](write-authority-audit.md)、[权限策略](permission-policy.md)、[迁移](legacy-write-migration.md)、[合同设计](task-contract-design.md)、[证据等级](requirement-evidence.md)、[剩余风险](remaining-risks.md)、[后续边界](next-stage-readiness.md)。
