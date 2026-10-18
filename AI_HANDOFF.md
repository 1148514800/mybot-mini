# AI Handoff

## 当前目标与状态

Phase22 Autonomous Coding Task完整完成：80自主专项、649全量及原断言、四旧基准、真实动态案例、唯一Tag/ZIP、APFS解压与独立还原均通过。分支codex/phase-22，工作树`/Users/godblack/.codex/worktrees/phase-22/mybot-mini`；基线Phase21 3063196。原main仍3461dc7，用户app.py/USER.md与原Index哈希不变。等待新任务，不Push/Merge/进入23。

## 实现与架构

- coding.autonomy默认关闭；开启需coding enabled+patch write+明确命令模式。六严格预算默认20请求/48工具/3Patch写入/6命令/3无进展/300秒；未知字段/非整数/非法组合拒绝。不扩大ReAct、授权或MCP/Skills/持久化。自主Gateway禁用SDK隐式重试。
- 原Loop可选CodingTaskController，无第二循环/Reviewer；按任务新建，finally清除并恢复命令guard，/clear/取消/异常/Session不恢复执行。精确原生工具类型才提供Patch/测试证据，MCP/模型文本不能伪造。
- 整批执行前预算检查，一批最多一项原生写入或命令；停止后配齐全部ID。不可逆规范化摘要检测重复，失败反馈由模型决定下一步；每次命令仍独立批准，不自动重试/回滚/Git操作。
- Patch实际发布增加revision并记录SHA；新Patch/哈希不符使旧验证失效。受识别有效argv+真实批准/启动/完成/零退出+非零测试数量+启动/结束/最终哈希才可verified。过早回答最多一次正常预算内补充请求，宿主确定性最终报告。
- guard在审批后/自检后重检期限、只收紧运行超时，不取消input线程。保留Phase19～21安全机制、Plan非零反馈、原Context/Session/Discovery。

## 文件与实测

共15文件：新增Controller、coding_agent评测/JSON案例、三个CLI/专项与phase-22文档；修改Loop/config/run_command可选guard、模板/check_phase、README/索引/本交接。完整文件表、函数/流程、配置、状态和限制见docs/phases/phase-22.md。Patch/Planning/Session/ContextManager/MCP实现未改。

80专项、649全量（569+80）及Phase1/2原断言、58命令/55Patch/34Repository/25MCP Approval专项、编译/确切归档集成通过。四组基准与Phase21除六个计时/Git字段逐字段相同。

真实动态19/19符合预期安全结果：5 verified、4 unverified、4 blocked、3预算停止、3无修改，false_verified=0/missed=0。合计91请求/73工具/10Patch发布/25命令尝试/20测试运行，Token/费用null；单文件7请求/6工具/1Patch/2测试，真实exit1→0，1项通过；多文件单Patch两文件通过。host_confirm对照18/18，沙盒不可用案例单列不适用。合成策略不代表真实LLM能力。无真实LLM/第三方MCP/OAuth。

## 归档与独立还原

功能提交f1de6107fd96192c286aa2272e86cd59763ed39e；归档源aa74730f0d347956c80c376db0d83b76ac447c28（仅补齐文档），唯一Annotated phase-22固定指向它，Tag对象7355f4d1a15fba20ca9ba13023e0e1a4cde341ce。发布事实另作后续纯文档记录，不移动Tag。

正式ZIP `/Volumes/move-disk/data/code/mybot-mini-snapshots/phase-22.zip`，SHA256 8bde581512362e7d9c70c53e50571ee5a1393ff34f5664252aa76bc65a45add6，173 entries/154 files；CRC、安全、提交SHA和逐文件等于Tag通过。脚本默认ZIP也保留在当前工作树同级snapshots。旧22 Tag/全部旧ZIP及原有元数据哈希不变。

正式ZIP独立APFS解压与restore学习目录`/Users/godblack/.codex/worktrees/phase-22/mybot-mini-learning/phase-22`，均冻结安装/编译/649全量/四基准/19例Evaluation/6例Demo通过；测试后154文件仍等于Tag。原main仍旧代码，新能力请在本工作树或学习目录查看；不覆盖用户文件来同步。

## 边界与下一步

本阶段无未完成项，等待用户新任务。只核验原生Patch涉及文件和指定测试，不能完整监测并发写入、MCP/外部副作用；host_confirm无OS隔离。测试输出非密码学证明，少量Python runner解析不等于整个项目正确。交互输入无法硬中断，任务时间在安全边界重检。沿用Seatbelt弃用、无硬内存/总磁盘配额/恶意脱组后代完整回收等限制。真实模型/Token/费用未测。不要重复实现、移动旧Tag/覆盖ZIP或混入用户修改，不自动Push/Merge/Phase23。
