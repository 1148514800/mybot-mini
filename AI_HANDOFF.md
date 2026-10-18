# AI Handoff

## 当前目标与状态

Phase22实现与开发验收完成，正在执行不可变归档与独立还原验证。独立分支codex/phase-22，工作树`/Users/godblack/.codex/worktrees/phase-22/mybot-mini`，基线Phase21 3063196。原main仍3461dc7，用户app.py/USER.md与原Index保持开始时哈希；不Push/Merge、不进入23。

## 实现与架构

- coding.autonomy默认关闭；显式开启需enabled+patch write+明确命令模式。六类严格整数预算，未知字段/类型/权限组合拒绝；不扩大ReAct、不自动开MCP/Skills/持久化。原Schema/默认行为保持。
- 可选CodingTaskController接入原Loop，无第二循环/Reviewer；每任务新建，finally清除并恢复原命令guard，/clear/取消/异常/Session不恢复执行。只接受Registry精确原生类型的Patch与命令证据，MCP/模型文本不能伪造。
- 整批预算预检查，一批最多一项原生Patch写入或命令；超限/中间停止为全部ID补失败结果。六预算和有界不可逆重复摘要；模型决定下一步，每次命令仍独立批准，不自动重试或Git回滚。
- Patch发布增加revision并记录after_sha256，后续Patch使旧验证失效。可信有效argv、真实批准/启动/完成/零退出/非截断、非零测试数量和启动/结束/最终安全文件哈希共同验证；只支持少量Python unittest/pytest形态。模型过早结束最多一次预算内补充请求，最终输出宿主确定性状态。
- 命令guard在审批后/自检后重检任务截止时间并收紧运行超时，不取消CLI input线程。保留Phase19～21安全机制、Plan非零反馈及原Context/Session/Discovery。

## 文件与验证

新增Controller、reactive coding_agent评测/JSON案例、三个CLI/专项脚本和phase-22学习文档；修改Loop/config/run_command可选guard、模板/check_phase、README/阶段索引/本交接，共15文件。原Patch/Planning/Session/ContextManager/MCP实现未改。

80专项已通过；真实动态19例全部符合预期安全结果，5 verified、4 edited_unverified、4 blocked、3预算停止、3无修改，false_verified=0/missed=0。单文件7请求/6工具/1Patch/2测试，真实失败→修复→通过；多文件单Patch2文件正确验证。整体91请求/73工具/10Patch/25命令尝试/20测试运行；Token/费用null。测试读取与数值解析并非密码学证明。无真实LLM或第三方MCP/OAuth。

58命令/55Patch/34Repository/25MCP Approval专项、编译通过；归档脚本集成通过。四组旧基准与Phase21除计时/Git元数据逐字段相同。最终冻结代码649全量及Phase1/2原断言全部通过；独立归档验证待执行。自主模式SDK禁用隐式重试。

## 边界与下一步

下一步从干净实现提交执行save_phase.sh 22，唯一Tag/ZIP、APFS解压与restore全量验证后另作纯文档记录。开发验证已满足archive-ready；独立归档尚未完成。日志在/tmp/phase22-*，不提交。

只核验原生Patch涉及文件和指定测试，不能完整监测所有并发写入、MCP/外部副作用；host_confirm无OS隔离。总时间在交互审批返回后重检，不能强制中断input线程。沿用Phase21 Seatbelt弃用、无硬内存/总磁盘配额/恶意脱组后代保证等限制。动态教学规则不是通用LLM能力，真实模型/Token/费用未测。不要移动旧Tag/覆盖ZIP或混入用户工作。
