# AI_HANDOFF

## 当前目标与状态

Lean Core v2 已完成实现与离线验收，分支 `codex/lean-core-v2`，基线 `bb4a5f4311f4e98936e0bd206986ccbdb00ee4b3`。交付提交即本快照所在提交；Implementation/Acceptance SHA用 `git rev-parse HEAD` 查询。完整合同、迁移步骤和实测数据见 `docs/lean-core-v2.md`。本轮不是Phase，不创建Tag/ZIP。

## 已完成与架构合同

- 生产 WriteFileTool、旧文件审批和 legacy_confirm 权限路径退役，过期调用固定 TOOL_RETIRED_WRITE_FILE；保留原生 Patch/Receipt、审批和Seatbelt核心实现。
- Session只支持memory（默认）/event_sqlite；独立迁移脚本读取旧JSON，默认预览、显式apply、新DB独占发布、失败保全；工具历史默认拒绝，有损转换需双标志和备份，不恢复执行状态。
- Token默认estimate/16000，关闭context也计量，strict未验证Tokenizer时拒绝。legacy_chars须确认语义变化，迁移不扩大input_limit。
- config_from_document/load_config统一CLI/Web/check合同，无导入时配置读取或Provider全局状态。显式GatewayConfig继续支持；旧关键字/字段明确不兼容。
- MCP/Skills禁用时不初始化manager/transport/SkillRegistry；启用时owning task不变。同一AgentLoop、Failover预算与宿主门、Streaming终态、WorkspaceLease继续保留。
- 生产109→108文件，14052→13834行，+305/-523净减218；没有新增生产模块。

## 实际验证

全量 `scripts.check_phase`：61组1752/1752通过，0失败/0跳过，354.89秒。核心 `scripts.check_core`：234/234通过，17.90秒。启动/Repo Map/新迁移专项：56/56通过，4.57秒。Python编译、两份JS语法、git diff检查通过。旧测试按退役合同迁移，冻结源码/历史评分不改，最终全量重新跑通。

同环境冷导入中位：app332.019→165.292ms，Web Runtime338.653→168.991ms；Mock请求0.439→0.468ms，始终预算计量略有开销，不宣称请求提速。真实模型请求0。

## 下一步与边界

用户实际配置/数据尚未迁移；按文档先预览并备份，数据成功后才显式切换SQLite。大型Schema可能超过默认16000，不能自动增额；strict暂无验证Tokenizer；不合并已有DB，隐私规则改变文本时拒绝迁移。真实Provider、历史Operator未做Live验收，不要重复启动Campaign或重评历史。

原main工作树未改：HEAD `8c1a049904f9544fc5eaeb53c06f6712e43ea320`，保留app.py/USER.md原未提交修改。真实config、历史报告/冻结证据/Fixture数据/Gold/账本/Tag/ZIP不动。共享ExFAT Git有AppleDouble pack index警告，未改共享元数据。本分支按用户授权Commit/Push，最终远程核对结果见交付消息。
