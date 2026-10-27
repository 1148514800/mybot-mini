# Coding Agent真实工作流Canary v1

未编号工程专题，不创建历史Tag/ZIP。目标是从用户任务到原生调查/Preview/Receipt/Patch/批准命令/当前Revision测试/独立功能验收的完整链，而非模型自述成功。

核心调用：browser.run（新独立Chrome真实DOM）→端口单socket/归属/ready→server.owned_app→create_app/ChatRuntime→原AgentLoop/CodingTaskController→原ToolRegistry/ApplyPatchTool/RunCommandTool→ProviderFailover/SDK。额外Native scope wrapper只拒绝非注册路径/argv，保留原始原生对象和Authority；IntegrityGate对实际Journal/Revision/字节/Git元数据做宿主审计，非第二个AgentLoop。

fixture.py构造notesearch-mini及真实Bug。工作区仅公开5文件，可写仅notesearch/search.py。prepare先在Seatbelt验证基线失败/Reference通过，再建立新workspace/私有两库；freeze锁住HEAD/Fixture/模型/源码/评分/身份。每请求前验immutable与当前合法Revision。score复用原隔离grader，绝不在宿主导入候选；隐藏10项在模型结束后运行，输出不回模型。

预算12模型请求、40工具、2 Patch写尝试、2命令、4无进展、600秒；命令30秒/32768字节、Web任务900秒。未来GRANTED_12_REQUESTS只授模型额度；人必须逐次批准原命令弹窗。Mock以SYNTHETIC_APPROVAL验证真实命令/沙盒路径，不能冒充人批准或模型真实编码能力。

macOS/Python3.12+/uv：`uv sync --frozen`；`uv run python -m unittest scripts.check_coding_workflow_canary_v1`；`uv run python -m scripts.check_phase`；报告列出的独立补充检查；compileall与node --check。Chrome合成：`uv run --no-project --with playwright python -m scripts.coding_workflow_canary_v1.browser --chrome <现有Chrome> --output <新私有目录>`，默认Mock且固定8903，不安装Fixture依赖或运行setup。

案例与排错：小只读上下文不能容纳Coding Schema或完整Receipt；需在预注册前固定足够但有界的预算。/private/tmp可能继承wheel，新Fixture明确设置当前组，不能关Patch ownership校验。waiting_approval是活跃状态，不可被操作器误判终态；主异常与清理错误分别保留。Stop后已提交Patch仍在，未验证或uncertain不能假称回滚/成功。

最终离线数量/真实Chrome/唯一冻结及审批边界见[报告](../reports/coding-workflow-canary-v1/acceptance-report.md)。原N01/N02 PASS/旧T01 FAIL及旧私库、Phase25 Benchmark、main/Tag/ZIP不动。

最终：2142个去重unittest通过（新增45），完整check_phase程序式断言和独立补充实际执行，源码前后hash一致；headed Chrome固定8903 Synthetic闭环与双Profile隔离通过，Public5/Host10、Controller Revision1 verified，但真人批准维度false/真实Strict未执行。正式新批次唯一prepare/freeze/verify完成，332源码、配置/初始Git/workspace/两库身份一致，Revision0、0 Attempt/reservation/HTTP，停在授权门。实现SHA d679d21914adc1e8b9a758b2611d1b35d80c4c2c；预注册/冻结SHA 0807b612e734c212588045107ba33f992adecba0。

archive-ready: true
