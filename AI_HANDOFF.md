# AI Handoff

## 当前目标与状态

Phase17 Adaptive Tool Routing已实现，30项专项、原39 Discovery/17 Retrieval/24 Harness通过；全量最终384项、Phase1/2原断言及归档安全检查通过，phase-17 Tag/ZIP及独立还原验证完成。不运行Live、不Push、不进入Phase18。Phase16已按用户要求Push（main f5e7fad/phase-16）。保留用户mybot/app.py三处注释和workspace/instructions/USER.md未提交修改；旧16阶段Tag对象/ZIP哈希已核对不变。

## 实现与架构

- discovery新增可选routing_mode（缺省manual）、eager_tool_threshold（缺省4，0–64）、preselect_limit（缺省min(3,max_active_tools)，显式1–max_active_tools）；adaptive必须显式discovery.enabled=true，旧默认对象形状不新增键。模板保持manual/literal，不改真实config。
- router.py纯本地一次首轮决策，Catalog/索引不重复建。基础Context不可容纳沿原异常；空目录no_mcp_tools；4096字符上限/控制字符拒绝检索走manual_fallback；小目录满足数量/完整Schema/总Context预算才small_eager；否则同ranked_names正分排序贪心选最多preselect_limit，放不下跳过，无候选或全放不下则manual_fallback。无新LLM、MCP调用或审批。
- Catalog共享原Literal/BM25/Hybrid排序，retrieval.py/aliases未改；apply_preselection复用原原子验证。AgentLoop仅首轮挂接，手动activate仍完整替换且后续不自动覆盖；请求快照/Plan证据/执行权限不变。finally清空active/含名称决策，仅安全计数诊断供评测。
- Router只接收当前用户文本/Catalog/预算视图，不接Case/Gold/脚本；历史messages/turns/plan仅供原Context.prepare只读预算，不作检索query。Spy与Gold Canary验证边界、canonical状态不改。完整Schema不裁剪，Context关闭仍守专用数量/Schema上限。
- 扩旧Harness adaptive_hybrid/bm25，默认MODES不变；专用compare_adaptive_routing入口默认eager/progressive_hybrid/adaptive_hybrid。FixedClient只在本轮目标真实可见时跳过预声明探索动作，缺失仍搜索/激活，搜索miss不靠Gold修复。12例Prompt/Gold/脚本与phase16相同，仅新增category/language元数据。
- 独立preselection_count/hit/recall、direct MCP、模型手动探索段数和Router初始fallback数、路由耗时；自动不伪造显式retrieval/activation，未显式调用时Adaptive相应为null。有明确preselection_miss诊断，补救成功不当失败。中断前实际路由工作计入数量/耗时，命中率只用完成正例。原Live双开关、SDK retry=0、共享预算、Usage/隐私/owner Task不变。

## 文件

新增mcp_client/router.py、scripts/compare_adaptive_routing.py、check_adaptive_routing.py、docs/phases/phase-17.md；修改discovery、loop、evaluation/tool_agent、evaluate_tool_agent CLI、check_phase、两模板、case分类元数据、README/索引/本交接。Registry/ContextManager/Planning/Session/Manager/Adapter/认证/Phase9评分/检索算法词典/依赖均未改。

## 验证与实测

30项专项覆盖配置/两层预算/跳过候选/权限/Gold边界/首轮/手动覆盖/快照/Plan证据/生命周期/真实审批/真实MCP取消清理/三模式评测/Live兼容。mybot/scripts编译通过（清理24个确认AppleDouble）；原17 Retrieval、39 Discovery、24 Harness专项通过。最终全量384项及Phase1/2原断言、归档安全检查通过；中断预算额外定向1项通过。

本轮同代码12例三模式全部12成功、36完整样本、12配对：eager25请求/1461425 Schema字符，progressive_hybrid51/175363，adaptive_hybrid25/176425；业务调用均13。Adaptive自动预选合计31，10个正例Hit/Recall均1，Direct13，模型探索0，Router初始fallback1。无匹配agent-11误选1个无关候选但无业务执行；简单问答agent-10空集合fallback但模型不探索。Adaptive比Progressive多1062 Schema字符，不能宣称各指标都赢。旧检索报告逐项一致，旧默认Agent统计重新运行仍25/49/51请求、成功12/11/12。Token/费用/Live能力未知；无真实LLM或第三方MCP。计时和全部分组见phase-17文档。

## 归档与还原

实现提交531bdc1b634e40a4057f40ffe03e2344e2858c3f，唯一annotated phase-17指向该提交；../mybot-mini-snapshots/phase-17.zip共139条目，SHA256 0544447c5990589731fa99a13c271cb6a7c45937437e3abb4644c84e84e133f8。APFS独立ZIP与../mybot-mini-learning/phase-17还原目录均通过冻结安装/编译/384项及原断言；还原另编译scripts并重跑旧检索、旧默认Agent及新三模式。除计时/Git元数据外全部报告字段一致；清理140个确认AppleDouble。CRC/提交SHA/必要文件/无元数据/用户文件已提交版本核对通过；旧16个Tag/ZIP不变，临时worktree已移除。最终记录另作文档提交，不移动Tag。

## 限制与下一步

贪心/词法/小词典不是语义置信度，普通措辞可漏选多工具、无匹配任务可误选；固定脚本不是真实模型，ID评分不通用。预算预检查只保证首轮，后续仍可能超总Context；静态目录/全Server启动不变。Manager旧审计窗口256，饱和时Direct保守null。阶段完成，等待用户下一项任务；主工作区仅保留用户app.py/USER.md未提交修改。学习历史只在docs/phases和Git。不覆盖用户修改/旧Tag ZIP、不Push、不进入Phase18。
