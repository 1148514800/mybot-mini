# AI Handoff

## 当前目标与状态

Phase24 Real-Model Coding Benchmark实现完成，109专项/859全量及最新178859f的ZIP-only独立还原均通过；待正式Tag/ZIP和双副本最终验证，不能标Phase完整完成。分支codex/phase-24，工作树`/Users/godblack/.codex/worktrees/phase-24/mybot-mini`，准确基线dfd3461。原main仍3461dc7，用户app.py/USER.md和原Index、旧Tag/ZIP哈希在`/tmp/phase24-baseline.json`核对不变。不Push/Merge/进入25，不执行任何真实付费Live。

## 实现与架构

新增coding_fixtures/judge/live/metrics/benchmark与3脚本；12个独立标准库Python任务，难度各4，2公开/4隐藏。严格manifest、RuntimeCase仅公开字段；hidden/reference不进Agent。每Case/Repeat新临时Git仓库，原Loop/Controller/Registry/工具Schema不改；Journal开、Undo/MCP/Skills/Session持久化/debug关。

Judge在Agent结束后用可信公开测试与最终生产源码另建副本，再注入隐藏测试，真实Seatbelt/run_process/时限/输出与进程清理；非零实际计数和结构化回执，不信模型文本。完整文件/保护/Index/Journal/可信资产及最终版本检查，常见unittest篡改检测。逐级dir_fd/O_NOFOLLOW快照；未知新增文件名仅摘要。没有任意同进程解释器操纵的形式化防作弊证明。

Live双标志+凭证+TTY+真实沙盒后才build_client，重试0，模型命令保持逐次CLI审批；禁止Live合成Client/自动批准覆盖。复用Trace/Token/价格；全局和每任务预算，未知Usage/价格为null，估价上限非账单硬限。元数据报告独占写入runs/coding_benchmark，不保存原始对话/源码/隐藏正文/SDK错误/HOME路径。

## 实测

最终数据集全部Baseline隐藏有失败、Reference公开24/隐藏48全通过；CSV含LF/CR/CRLF，缓存验证无关键不失效，邮箱输入域明确字符串。109专项、859全量（旧750+109）及原断言、34Repository/55Patch/58Command/80Autonomy/101GitWorkflow/25Approval、编译和归档集成通过。四旧基准与dfd3461除六计时/Git字段逐字段一致。

默认离线12/12完整评分，12合成请求、0修复，无文件/Index/归属/协议异常；四路径Demo真实结果正确（修复hidden_pass、公开过拟合verified但hidden_fail、口头伪造无分、注入grader_error）。ability_score=false、real_model_repair_rate/Token/费用null。真实模型编码能力未测，没有实际API费用，禁止冒充Live成绩。

## 预还原与下一步

实现fafab78，修正源`178859f3340c9a00fb9808eed76af3f446af3634`。在添加archive-ready前已从干净修正源导出私有ZIP，使用原restore脚本的ZIP-only分支独立还原到`/private/tmp/mybot-phase24-preflight-x380wel9/mybot-mini-learning/phase-24`；859全量/原断言/四旧基准/12离线/四Demo及278源文件哈希全部通过。完整事实见phase-24学习文档。没有运行真实LLM或付费请求。

本次仅添加archive-ready/就绪状态，不修改代码；提交此文档后从干净HEAD执行save_phase.sh24，创建唯一正式annotated phase-24及完整ZIP。正式ZIP不可覆盖复制外置盘，APFS解压和正式restore再次执行`/tmp/phase24-verify-copy.py`的全套验证；最后纯文档记录提交，不移动Tag。不自动Push/Merge/进入25，不混入main用户改动，不重做已完成实现。最终验证前不能标整个Phase完整完成。
