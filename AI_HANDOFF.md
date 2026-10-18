# AI Handoff

## 当前目标与状态

Phase23 Git-Aware Coding Workflow完整完成：101专项、750全量及原断言、四旧基准、动态Demo/独立Evaluation、唯一Tag/ZIP、APFS解压和restore双副本验证均通过。分支codex/phase-23；工作树`/Users/godblack/.codex/worktrees/phase-23/mybot-mini`；基线Phase22 e117fd9。原main仍3461dc7，用户app.py/USER.md及原Index哈希不变。等待新任务，无Push/Merge/Phase24。

## 实现与架构

- coding.git_workflow默认双关闭；启用需coding+write+autonomy+checkout根；Undo额外需macos_readonly、关闭MCP、精确原生Patch-only Registry。默认Schema/路由/Session兼容。
- 首请求前只读Baseline记录HEAD、实际当前checkout Index、Git状态/完整性。普通Git和Worktree指针安全验证；不开放.git模型读取。仅支持SHA1完整v2/v3 Index，未知布局/格式、稀疏/split/子模块等保守禁Undo。
- Patch内部Observer发布前取真实Prepared A并预留预算；最终验证和清理后确认发布inode/字节/模式/属性再提交C。A→B→C合并A/C。有界私有镜像，不写metadata/Session/debug/持久文件，执行不确定停止。
- 宿主/changes展示本任务累计Agent Diff、用户基线、当前版本及未知外部变化；默认只摘要。宿主/undo全批预检→独立一次枚举批准→完整重检→复用Patch Stage/replace/受限unlink/条件恢复，无Git写操作。冲突拒绝，未知恢复明确报告且保留并发用户内容。
- Undo消费Capsule、使旧verified失效，不复测；clear/新普通任务/异常取消/重启不恢复旧授权。没有跨文件崩溃原子性、原子CAS或完整副作用监视保证；host_confirm/MCP只允许review并标未知副作用。

## 实测与文件

19文件变更；完整文件表、关键函数/调用、配置、真实案例、学习命令、支持范围见docs/phases/phase-23.md。新增Baseline/Journal、Undo/独立批准、合成Evaluation/16JSON案例、专项/评测/Demo和阶段文档；Loop/Patch仅小接线，原Controller/命令/MCP安全机制保留。

101专项、750全量（649+101）及Phase1/2原断言、34Repository/55Patch/58Command/80Autonomy、编译、归档集成通过。16例Evaluation全部符合安全预期，false_owned=0、unintended=0、Index保留16/16，5Undo完成/4冲突/1拒绝/1部分失败；Demo3/3。评分器额外文件反例能检出非预期变化。真实Seatbelt/测试，无真实LLM/第三方MCP/OAuth，Token/费用null。四旧基准与e117fd9除六计时/Git字段逐字段一致。

## 归档与独立还原

实现/归档源`edda5426534eaffe1ffb303f69fb855a9ebe482e`；唯一annotated phase-23固定指向它，Tag对象`58e43675638404da2f851f91856b83e74922a6df`。本交接为后续纯文档发布记录，不移动Tag。

正式ZIP `/Volumes/move-disk/data/code/mybot-mini-snapshots/phase-23.zip`，SHA256 `96d546cc1db18be067299b93b4cc3a805de053371d62d77f637aca5c1e069626`，183 entries/164 files；CRC/安全/注释提交SHA/逐文件等于Tag通过。脚本默认ZIP也保留在本worktree同级snapshots。旧23个Tag/全部旧ZIP哈希不变。

正式ZIP独立APFS解压及学习目录`/Users/godblack/.codex/worktrees/phase-23/mybot-mini-learning/phase-23`均冻结安装/编译/750全量/四基准/16Eval/3Demo通过；测试后164源文件仍等于Tag。原main旧代码未覆盖，新功能请在本worktree或学习目录查看。

## 边界与下一步

本阶段无关键未完成项，等待用户新任务。仅确认原生Patch目标和受支持Git元数据，不完整监视外部副作用；无原子CAS/跨文件崩溃事务/进程总内存硬配额。非支持Index/特殊布局或分支名、无HEAD等保守拒绝。沿用Phase21 Seatbelt弃用/资源和脱组后代回收限制。真实模型能力与费用未测。不要重做已有功能、移动旧Tag/覆盖ZIP、混入原用户修改；不自动Push/Merge/进入24。
