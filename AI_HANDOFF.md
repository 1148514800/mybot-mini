# AI_HANDOFF

## 当前目标与状态

Decision Provenance & Temporal Validity v1已实现并通过离线及独立Chrome合成验收，真实DeepSeek/GLM/摘要/Judge/Provider HTTP均0，不使用旧剩余1次。分支codex/decision-provenance-temporal-validity，基线ba04931815c222543a7e05bf86147a9a5adb4642；实现与验收报告分两个提交交付，报告目录docs/reports/decision-provenance-temporal-validity/。

## 实现与架构

新增agent/decision_provenance.py与storage/decision_timeline.py：精确SQLite user来源/Unicode跨度/确认事件，与普通原文和未验证分类提议分开。模型自由文本不成为Pin或宿主可信决定。SessionHistory.decisions复用于Web状态与CLI `/decisions [boundary]`。

事件Schema仍v1；数据库v2新增event_commits，和append_many同事务写提交区间。历史按真实提交终点查询，拒绝原子替换中间序号；v1迁移只记录当前可证明边界，更早未知端点null，禁止推断。部署需停止同库旧版本写者，旧程序不能直接降级读v2。本轮只迁移临时合成库，未打开用户/Live旧库。

Context Projection保留原来源遮蔽、独立事实与工具配对，增加自然语言来源/历史政策与有界提交顺序。Web显示来源与历史生效详情，模型回答明确独立于宿主确认；不改变Pin写入口、Tool Authority、CSRF/CSP或生产依赖。

## 验证与完整性

新增56项：来源20、时间线20、上下文16。最终check_phase 55组1637项，独立补充79、持久会话预算22、Source-Aware预算28，总计1766项，0失败/跳过；定向重复不重复计数。compileall、JS语法、diff检查通过，最终Python/JS源码前后哈希一致。初次全量因运行中编辑触发旧冻结门而作废，已稳定源码完整重跑。

Chrome152.0.7977.83/Playwright1.64.1 headed，新0700 profile及双profile Cookie/LocalStorage动态隔离通过。真实页面完成两约束确认、错误模型回答不污染、替换、撤销、跨七轮和重启；12次本地SyntheticClient调用。自身服务exit0、端口/Lease释放、profile清理，旧8765与用户Chrome未操作。原Live报告、冻结资产、Tag/ZIP及所有旧断言保留。

## 已知限制与下一步

不具备通用语义蕴含检测、实时改写模型错误或清除助手语义影响的能力。内部元数据为兼容仍在参考中，减少标签抄写尚未真实模型验证。旧库早期提交边界无法补造；预算仍可省略历史。当前样本参考独立估算1690–1769 Token，较同元数据旧参考增517–558，非供应商Token。

后续如需DeepSeek验证推断强化、可选/未决分类、历史时态和标签呈现，应另行预注册及授权新Live；不得重跑S01/S02/S03、改旧评分、动旧批次或消耗旧余额。Source-Aware旧Live最终Task3/3且12/12来源保留，但全程Decision Classification FAIL与助手语义影响UNKNOWN仍保持。
