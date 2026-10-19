# AI Handoff

## 当前目标与状态

Phase24 Real-Model Coding Benchmark实现完成，最新109专项通过，原750/先前859全量通过；最新确切提交的集成验证待独立还原与正式归档，不能标Phase完整完成。分支codex/phase-24，工作树`/Users/godblack/.codex/worktrees/phase-24/mybot-mini`，准确基线dfd3461。原main仍3461dc7，用户app.py/USER.md和原Index、旧Tag/ZIP哈希在`/tmp/phase24-baseline.json`核对不变。不Push/Merge/进入25，不执行任何真实付费Live。

## 实现与架构

新增coding_fixtures/judge/live/metrics/benchmark与3脚本；12个独立标准库Python任务，难度各4，2公开/4隐藏。严格manifest、RuntimeCase仅公开字段；hidden/reference不进Agent。每Case/Repeat新临时Git仓库，原Loop/Controller/Registry/工具Schema不改；Journal开、Undo/MCP/Skills/Session持久化/debug关。

Judge在Agent结束后用可信公开测试与最终生产源码另建副本，再注入隐藏测试，真实Seatbelt/run_process/时限/输出与进程清理；非零实际计数和结构化回执，不信模型文本。完整文件/保护/Index/Journal/可信资产及最终版本检查，常见unittest篡改检测。逐级dir_fd/O_NOFOLLOW快照；未知新增文件名仅摘要。没有任意同进程解释器操纵的形式化防作弊证明。

Live双标志+凭证+TTY+真实沙盒后才build_client，重试0，模型命令保持逐次CLI审批；禁止Live合成Client/自动批准覆盖。复用Trace/Token/价格；全局和每任务预算，未知Usage/价格为null，估价上限非账单硬限。元数据报告独占写入runs/coding_benchmark，不保存原始对话/源码/隐藏正文/SDK错误/HOME路径。

## 实测

最终数据集全部Baseline隐藏有失败、Reference公开24/隐藏48全通过；CSV含LF/CR/CRLF，缓存验证无关键不失效，邮箱输入域明确字符串。109专项、859全量（旧750+109）及原断言、34Repository/55Patch/58Command/80Autonomy/101GitWorkflow/25Approval、编译和归档集成通过。四旧基准与dfd3461除六计时/Git字段逐字段一致。

默认离线12/12完整评分，12合成请求、0修复，无文件/Index/归属/协议异常；四路径Demo真实结果正确（修复hidden_pass、公开过拟合verified但hidden_fail、口头伪造无分、注入grader_error）。ability_score=false、real_model_repair_rate/Token/费用null。真实模型编码能力未测，没有实际API费用，禁止冒充Live成绩。

## 下一步

初始实现已提交fafab78；补齐基于真实工具行动的no_code_change分类后，后续预还原以最新确切提交为准，当前不得有archive-ready行。运行`/tmp/phase24-preflight.py`：从干净确切提交导出私有临时ZIP，使用ZIP-only restore到APFS独立目录，`/tmp/phase24-verify-copy.py`验证859全量/四基准/全12离线/四路径Demo。成功后才添加archive-ready并作就绪文档提交；从干净就绪提交save_phase.sh24创建唯一正式Tag/ZIP。正式ZIP不可覆盖复制外置盘，APFS解压和正式restore再次完整验证；最终纯文档记录提交，不移动Tag。当前源文件278个，Code已冻结，不重复实现或修改旧750断言。详细结构/CLI/学习/限制见docs/phases/phase-24.md。
