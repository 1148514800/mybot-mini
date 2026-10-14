# AI Handoff

## 当前状态

Phase09 Evaluation2.0 已实现并离线验证，待 Commit/phase-09/ZIP独立归档。Phase01–08 Tag/ZIP不变，不进入Phase10，不自动Push。未执行新增Live API。

## 实现

- evaluation/grader.py：task_success只看正常结束与实际结果；process_clean区分非预期失败/Plan未完成；instruction_followed验证明确Plan/Skill要求；strict_pass合取。Auto无强制技能。复杂审查按文件+函数+证据评分，文档整合核对最新/过期/约束/无来源信息，人工审查另标。
- trace.py：固定真实Planning错误安全分类、规划失败/前置文件工具/归一重复读取、技能加载/参考/带技能请求用量；边际成本unknown/null。观察不改Phase4状态机或Tool执行。
- runner.py、CLI：JSONv2、Off/Auto/Guided、case-ids选择，全局限额共享。Off/Auto提示一致；Guided显式先加载、无相关技能跳过，独立工作区/历史/工具。Offline不再自动假装Auto选Skill，Guided固定脚本明确标记。
- history.py：v1报告只读重解释，缺失Planning原因unknown，无原文产物不能完整重新评分。evals/cases.json增加四文件代码审查和四文档整合，共12例。
- check_evaluation.py原18项更新评分语义；check_evaluation_v2.py新15项；统一回归接入；教程/索引/README更新。无新依赖或Agent功能。

## 验证

33项评测测试与Phase01/02、Session12、Planning12、Persistence16、Context18、Skills16均通过，编译通过。完整Offline：Off12/12、Auto12/12（各25工具/37请求、无Skill）；Guided4/4（20工具/24请求、4脚本加载），Token=null，不是模型能力成绩。用户旧报告只读重算Off任务6/6/clean6/6/strict6/6，Auto任务6/6/clean5/6/strict5/6，Planning unknown2；原SHA256未变。归档安全检查通过；待独立快照验证。

## 局限

严格JSON/证据片段可误拒合理改写，解释/建议需人工；非通用语义Judge。Guided提示不同，收益不能单因果归给Skill。未新增真实Live，精确技能净增请求/Token未知。历史报告无原产物/回复/错误，不能补猜。重复读取只是效率统计；不保存完整正文/错误/产物。v1/v2分数不能直接比较。

## 环境与用户修改

macOS、Python3.12+、uv。CLI uv run python -m scripts.eval_agent；--live须用户显式运行。默认Off/Auto前10例，复杂任务用case-ids或max-cases12。Session持久化/debug关闭，独立临时workspace，真实配置/Session与runs不归档。app.py/USER.md改动保留不提交。APFS独立验证，ExFAT ._* 尽量减少/排除。

## 下一步

完成Phase09归档并记录真实SHA/验证，之后由用户指定。不要改旧Phase或旧报告，不进入Phase10；学习见docs/phases/phase-09.md。
