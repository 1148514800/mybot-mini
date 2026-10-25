# Source-Aware Context Projection — OFFLINE PASS

基线`e9f2e822e5423742c3bf73194cb56f4fa1711869`；独立分支`codex/source-aware-context-projection`。Implementation：`892a1c31353cdd1b342a9c195d8d646efa5b0e7e`。本报告及证据由后续Acceptance提交交付，最终SHA和远程HEAD在交付回复核对。不合main、不改变历史Tag/ZIP或旧Live结论。

本轮只验证来源投影机制。DeepSeek、GLM、真实语义摘要、付费Judge请求均**0**；未使用原Live余额，未启动原Live server或访问原私有SQLite。

## 验收结论

|问题|实际结论|
|---|---|
|1 原3/累计5来源损失是否改善？|PASS：原提交独立源码快照的实际SyntheticClient请求重现3/5；新源码两阶段均保留5/5用户事实，损失0/0。|
|2 是否仍整轮删独立事实？|可验证纯文本来源只遮蔽失效跨度；工具协议、来源失败和预算不足仍允许明确的保守省略，不承诺普遍零损失。|
|3 原SQLite历史是否不变？|新Fixture与原始事件/消息前后比较一致；新请求只追加新事件，原Live数据库未访问。|
|4 来源是否严格？|真实message ID+Session+user角色+Unicode跨度及内容验证；重复句子不合并身份，缺失/截断/脱敏/不一致明确回退。|
|5 助手旧复述如何处理？|精确完整原句复述保守省略并计数；其他历史助手内容标非权威/非用户确认，不能恢复失效Pin。|
|6 哪些语义未知？|隐含指代、跨句改写、模糊语义仍未验证；没有LLM分类器或物理遗忘证明。|
|7 Tool Call协议？|PASS：不受影响组ID/顺序/结果保持；受影响组整体省略，真实合成请求严格配对，无旧工具重放。|
|8 局部遮蔽诊断？|PASS：轮数未减也标incomplete/truncated，CLI与Web读取同一context统计；SSE无遮蔽原文。|
|9 同类Pin仍误报冲突？|PASS：multiple_same_category与semantic_conflict_unassessed，中性UI；不再自动needs_review或让Pin失效。|
|10 增加模型请求？|无新分类/冲突检测/摘要触发路径；全部真实请求0。既有可选语义压缩仍受原显式授权和预算门管理。|
|11 新权限/恢复风险？|未扩大权限，无schema/事件重写，无Receipt/审批/verified恢复；新参考占用原预算。|
|12 尚需真实DeepSeek验证？|助手语义改写与建议升格的实际影响、生命周期参考的真实遵从、Token压力下回答质量，均未Live验证。|

## 测试与真实浏览器

最终权威运行的Python源码前后哈希一致，0失败、0 skip：

- `check_phase`：52组**1581项**（原1539 + 新42）。
- 原独立补充7组：**79项**，没有重复加入已在check_phase中的专项。
- Persistent UAT离线预算/MockTransport门：**22项**。
- 去重总计：**1682 = 原1618 + 原新增预算22 + 本轮42**。
- compileall、JavaScript语法、git diff --check均通过。各模块构成、命令、时间与日志SHA见offline-validation.json。

新增专项为来源21、生命周期/AgentLoop12、协议9，覆盖精确/重复/Unicode/跨Session/重启/脱敏来源、5事实保留、助手复述、Token预算、SSE脱敏和协议回退。SessionEventStore、Recovery、Pinned、ContextProjection、Compactor、TokenBudget、TaskContract、ToolAuthority、Receipt、Coding Reliability、ProviderFailover及Web专项均在实际全量组合中执行。

真实headed独立Playwright Chrome的A–E合成验收通过：兼容Pin、替换、撤销、重启及工具历史。最终运行9次合成请求，全部实际请求协议校验通过；开发过程另有等待/截图复核，详见browser-acceptance，不计作真实API。截图经过目视脱敏检查，原用户Chrome/8765未操作，自己的服务与profile已清理。

## 兼容性与剩余问题

本轮发现原冻结observer用整轮对象相等比较计数，局部遮蔽会令它误报5/5损失。未修改observer或旧Live成功标准；离线预算E2E保留原3/5基线断言，并强化新请求5/5断言及真实来源遮蔽检查。后续独立Live需采用新诊断与实际来源单元核查，不能把旧observer误报当真实丢失。

Source Preservation改善不等于模型语义质量提升。助手未知改写仍可影响模型，精确复述省略可能丢失其它助手建议，协议/来源/预算回退仍可能损失事实。完整限制见remaining-risks；后续Live须另获明确授权。
