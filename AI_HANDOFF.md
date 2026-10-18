# AI Handoff

## 当前目标与状态

Phase23 Git-Aware Coding Workflow：实现、101专项、750全量及原断言、归档集成已验证；待唯一Tag/完整ZIP与独立解压/restore验证。分支codex/phase-23；工作树`/Users/godblack/.codex/worktrees/phase-23/mybot-mini`，基线Phase22 e117fd9。原main仍3461dc7，两处用户修改与原Index字节不变。无Push/Merge/Phase24。

## 实现与架构

- coding.git_workflow默认双关闭，启用需coding+write+autonomy+checkout根；Undo需macos_readonly、MCP关闭、精确原生Patch-only Registry。默认Schema/旧路由/Session兼容。
- 首请求前只读GitBaseline记录HEAD、实际当前checkout Index、状态/完整性。普通Git与Worktree指针固定校验；安全元数据读取不开放模型。仅支持SHA1完整v2/v3 Index，其他格式/稀疏/split/子模块等保守禁Undo。
- Patch可选内部Observer：发布前预算/真实Prepared A，全部发布验证和清理后确认发布inode/字节/模式/属性提交C。A→B→C合并A/C，有界私有镜像，不写metadata/Session/debug/磁盘。执行不确定停止。
- 宿主/changes展示原生Patch累计Diff、用户基线、当前匹配、未知其他变化；默认任务只摘要。宿主/undo完整批预检→独立一次枚举批准→完整重检→复用Patch Stage/replace/受限unlink/条件恢复；不调用Git写操作。外部接管/HEAD/Index变化拒绝，部分失败明确报告，保留并发用户内容。
- Undo消费Capsule并使原verified失效，不复测；clear/新普通任务/异常取消/重启无旧授权。无跨文件崩溃原子性、原子CAS或完整副作用监视承诺。host_confirm/MCP仅review且标未知副作用。

## 实测与文件

新增Baseline/Journal、Undo/独立批准、合成Evaluation/16JSON案例、3CLI专项/评测/Demo与phase-23学习文档；修改Loop/Patch小接线、config/app、模板/check_phase、README/阶段索引/交接。详细文件表/函数/调用/学习案例/命令/限制见docs/phases/phase-23.md。

101专项、34Repository/55Patch/58Command/80Autonomy、编译通过；16例Evaluation全部符合安全预期，false_owned=0、unintended=0、Index保留16/16；Demo3/3；真实Seatbelt和测试，没有真实LLM/第三方MCP/OAuth，Token/费用null。四旧基准与e117fd9除六个计时/Git字段逐字段一致。750全量（649+101）及Phase1/2原断言、归档集成通过；最终发布记录待补。

## 下一步与不要重复

源码已完成验证与archive-ready；提交后save_phase.sh 23创建唯一annotated phase-23及完整ZIP，不覆盖同名目标；正式ZIP必须不可覆盖复制到外置盘snapshots。独立APFS解压与restore均冻结安装/编译/全量/四基准/Demo/Eval，再做纯文档归档事实提交，不移动Tag。再次核验原main、用户文件/Index、旧Tag/ZIP。完成后停止，不进入24、不Push/Merge，不重做已有功能或混入用户改动。
