# AI Handoff

## 当前状态

Phase 08 Evaluation 已完成并独立归档；phase-08 指向 8897e71af3884e7eec1597b8cf4417159a15c1cb。ZIP：../mybot-mini-snapshots/phase-08.zip。Phase 01–07 Tag/ZIP 不变，不进入 Phase 09，默认不 Push。没有执行真实 Live API。

## 实现

- mybot/evaluation/runner.py、trace.py、grader.py：复用 AgentLoop，临时工作区/独立 Session/ToolRegistry，固定 Offline 脚本和显式 Live；真实结果观察、确定性文件/事实/缺陷/Plan 评分。
- evals/cases.json：10 个合成可复现案例，技能自然任务描述，A/B 独立运行；scripts/eval_agent.py 提供次数/全局请求/整例超时/重复/输出目录。
- Trace 只存名称、白名单合成路径、成功/长度/耗时与裁剪统计；最终回复仅长度/哈希，API Key/正文/原始错误不保存；usage 缺失为 null。报告在忽略的 runs/evals。
- scripts/check_evaluation.py 18 项测试，check_phase.py 集成，test_phase_archives.py 夹具含 evals；教程/索引/README 更新。没有新依赖或修改正常 Agent 执行语义。

## 验证

Offline A/B 各10/10（机制验证非能力成绩）：A工具16/请求26，B工具18/请求28；两技能被模拟加载，Token=null。18 项评测测试通过；Phase01/02、Session12、Planning12、Persistence16、Context18、Skills16 全部回归通过，编译通过。归档安全检查通过；干净工作树 ZIP 冻结安装、编译及全部离线回归通过，restore_phase.sh 8 独立还原后再次验证及 Offline CLI 通过。ZIP 83 条目含评测代码/合成案例/示例技能/文档/锁文件，无配置密钥、真实Session或评测日志。

## 决策与局限

评测默认 Context 开启40000字符/工具1000，上限16 ReAct，A/B相同；Provider/Model沿配置。Persistence/debug强制关闭，不使用真实workspace/历史。Live须显式 --live，SDK重试关闭，max_requests为全运行总限额，timeout为整例。预期缺失文件允许特定失败，其他工具失败/未完成Plan/上限均不能成功。

Offline脚本知道答案，不能证明自动发现或模型能力；字面规则有限，审查解释需人工；无成本估算、全文Trace、产物保留、并行或LLM Judge。真实Live未运行。只读可信技能，运行时不要修改其内容。

## 环境与用户修改

macOS/zsh、Python3.12+、uv。运行 uv run python -m scripts.eval_agent；开发及归档只 Offline。app.py/USER.md 用户改动保留，不提交；配置/真实Session不输出归档。ExFAT ._* 尽量 COPYFILE_DISABLE=1，归档排除，独立验证APFS。

## 下一步

Phase08 已结束，之后由用户指定。不重新实现旧阶段，不进入 Phase09；学习原理见 docs/phases/phase-08.md。
