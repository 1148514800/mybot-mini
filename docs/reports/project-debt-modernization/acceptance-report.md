# 项目技术债现代化验收

**OFFLINE PASS**。原1293项测试全部保留；新增61项，完整1354/1354、38套件、零跳过。结论是核心Runtime达到受控下一阶段的离线工程门槛，不代表项目所有技术债消失、真实模型能力提升或Strict Success。

基线远程 `codex/web-chat-ui`：`1de96420122daf0d75a650952613a05d1ace99ac`。交付分支 `codex/project-debt-modernization`，Implementation与Acceptance分离；具体实现SHA在本文后续交付节。原main、Tag/ZIP、历史raw与原工作区用户改动不变。

## 实际交付

- 完整可见请求计量：字符、UTF8字节、本地估算、供应商Usage、未知状态分别表达；包括Schema/工具参数与结果/System/Skills/Plan/摘要。旧max_chars仍是字符。输出预留及主备不同窗口在发送前检查；strict无法验证就拒绝。
- 可选语义压缩：默认deterministic，显式semantic + allow_extra_requests才调用模型；九字段来源引用，低信任、不可恢复授权/验证，原Session不变；有界输入/输出/次数/超时/取消及共享Controller/Evaluation物理预算。当前只验证合成流程。
- CLI/Web/Trace共享每轮资源快照，区分logical/physical/HTTP attempts/已报告Token/估算输入；Usage缺失null，费用未知。失败Plan、取消/超限不包装成成功。
- 确认缺陷11项已修复：P0=0、P1=9、P2=2。覆盖SDK隐式重试、非暂时错误回退、计量口径、跨进程工作区冲突、配置继承、静默无界读取、UTF8字节数、Web失败状态、CLI异常载荷、capsule清理及会话切换竞态。另改善字符预算与规则摘要2项能力限制。

## 运行证据

单独执行新增 Token16、Compaction22、Accounting23项；原context/session/persistence/web_ui/coding_failover/coding_reliability/patch_preview_receipt全部通过。额外repository34、autonomy100项通过。完整入口追加三套专项后1354项通过，compileall与git diff --check通过。详细计数与日志摘要哈希见 offline-validation.json；未删除旧断言或跳过安全测试。

开发中发现CLI可选字段适配和SDK构造参数合同的两次回归，已修复后重新执行全量。旧构造器调用形式保持，真实返回SDK实例在任何请求前设置max_retries=0；不是放宽原测试。源码安全审核保留Controller/评分/Receipt/审批链原实现。

| 合成场景 | 实际链路 | 判定 |
|---|---|---|
| A 长对话 | 真实AgentLoop → 旧完整轮次摘录 → 合成语义引用 → 主请求 | 目标、新约束、待测试、未知保留；原Session未改；2逻辑/物理请求，其中摘要1 |
| B 长工具输出 | 原read_file读取长代码 → Context预算裁剪 → 工具ID配对 → 回复 | 明示节选，不声称全文；2请求，无摘要调用 |
| C Coding长任务 | search_code → read_file_range → Preview → 单次Receipt Commit → 原生Seatbelt测试 → 完成 | 当前Revision测试通过，6请求；原Controller报告verified，仅指指定测试范围，不宣称Strict Success |

每场景原字符预算、压缩前后字符/估算大小、保留与丢失信息见 before-after-comparison.json。这是同一合成请求的视图对照，不是重跑历史A/B，也不能推导真实节费收益。

真实浏览器通过127.0.0.1 HTTP/SSE发送一次合成长对话请求。页面实际显示：2逻辑/2物理调用、1摘要请求、合成Usage300、当前估算5067、窗口未知、裁剪警示。桌面截图 [browser-metrics.jpg](browser-metrics.jpg)；本轮未额外重做手机视觉验收，原Web自动回归仍保留。临时服务和标签页已关闭。

## 安全、费用与边界

真实模型API **0次**；人工PTY/nonce **0次**，浏览器实际审批 **0次**。自动测试中的受控审批回调单独处理，不冒充人工审批。不使用旧A/B额度，不复制真实配置/密钥。1560个保护文件哈希不变，main与全部Tag refs未变，未创建/改写ZIP；无新增依赖或模型权重。

DeepSeek-V4.1-Flash和GLM-5.3-Flash官方资源可查，但coco/coco2部署与Tokenizer/template/window映射未确认；目前精度为保守UTF8估算，local_tokenizer_tokens=null、费用unknown。推荐配置与启用方式见 [Context说明](../../context.md)。语义生产调用潜在新增费用必须由用户显式启用。

剩余8项：P1为部署Tokenizer映射、legacy文件TOCTOU潜在风险、不同工作区共用Session路径限制、真实语义质量；P2为Web内存历史、慢IO取消风险、特殊MCP名称检索风险、脱敏层次依赖。详见 remaining-debt.md。没有宣称项目全部READY；建议在独占工作区/独立Session路径下进入另行授权的真实日常验证。

报告索引：[架构](architecture-audit.md)、[债务登记](technical-debt-register.md)、[Token](token-accounting.md)、[摘要](context-compaction.md)、[安全](security-audit.md)、[下一阶段](next-phase-readiness.md)。

## Git交付

Implementation：`b0346bdfca3451101c8af65be7beeaf2c17baaa6`。Acceptance 为包含本报告的后续 `docs:` 提交；其SHA与推送后的远程HEAD在最终交付消息核对。只推送 `origin/codex/project-debt-modernization`，不合并main、不推Tag。
