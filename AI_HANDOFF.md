# AI Handoff

## 当前目标与状态

Phase21 Terminal Execution/Approval/macOS Sandbox已完整完成：58命令专项、569全量及原断言、编译、归档集成、唯一Tag/完整ZIP、独立解压和还原全部通过。停止等待新任务，不Push/Merge/进入22。分支codex/phase-21、工作树 `/Users/godblack/.codex/worktrees/phase-21/mybot-mini`，基线已推送Phase20 db50c67；原main仍3461dc7，用户app.py/USER.md与原Index哈希不变。

## 实现与架构

- coding.command默认off/30秒/32768字节，严格校验；非off需enabled，host_confirm还需patch_mode=write。显式Registry/Gateway关键字接线，旧默认Schema/Patch-only保留。独立CLI单次审批，仅ApprovalDecision.APPROVE；非TTY/无Provider/异常/敏感或无法完整展示参数拒绝，不缓存授权、不伪装MCP。
- 共享arguments有界解析器（Patch保留原限额），run_command解码前16KiB、32 argv、单项2048字符、总8192 UTF8、严格Schema/重复键/有限数/深度检查。固定可信Python或验证项目venv；uv仅固定run --no-sync python形态，完整有效argv含无配置/离线/固定解释器选项审批。cwd固定fd+审批后/自检后重核，运行时/venv指纹冻结。无Shell字符串、自由env/stdin/profile/身份输入。
- command_process独立于Phase19 runner：可信-I/-S资源引导器/CLOEXEC exec握手，最小环境、专属HOME/TMP/cache，双流合计预算、wall/CPU/单文件/FD限制，临时32MiB/512项监测，独立进程组、有限清理、取消传播和spawn竞态清理。已知路径/凭证标记和终端控制字符处理，不完整结果不冒充通过。
- macos_readonly使用真实sandbox-exec deny-first：代码/特定运行时只读，只有专属临时目录可写，网络/Mach拒绝，Workspace/Index不可写、已知私密路径不可读，hardlink/process-info拒绝，sysctl窄许可含vm.pagesize兼容项。每条批准后13项合成隔离自检（真实可达网络对照、别名、私密文件与子进程）必须通过才启动项目命令，无降级。host_confirm明确无OS隔离。
- 原Loop/Plan仅为可信RunCommandTool非零完成反馈保留in_progress并清除verified；不标safe_to_retry、不自动重复。审批/沙盒/超时/不确定状态停止批次并配齐ID；MCP原文案包括排队command场景保留。MCP/路由/OAuth/Context/Session架构和持久化默认未改。

## 文件与实测

新增arguments/command_config/command_approval/command_process/macos_sandbox/run_command六模块、check_command_execution.py、phase-21.md；修改config/app/registry/Patch解析/Loop/Plan、配置模板、coding_repo_demo/check_phase、README/索引/本交接，共20文件。完整文件表、核心函数/调用图、学习说明与限制见docs/phases/phase-21.md。

macOS26.6.2、Python3.12.14、uv0.12.10：58专项（含13项真实沙盒门控/父进程参数读取宿主对照/输出/超时/取消/进程组与脱组持管道边界）、55Patch、34Repository、25MCP Approval、569全量（511+58）及Phase1/2原断言通过。冻结安装、编译、最终归档集成通过。四组旧基准与db50c67除计时/Git元数据逐字段一致。

真实原Loop Demo12次固定模拟请求/2次合成单次审批：unittest真实exit1（-1!=5）→真实SHA/Patch预览与写入→同一测试exit0、1项通过；沙盒版两次true、host版两次false，Plan/ID配对正确，注释/暂存README/未跟踪notes/Index保留。正式ZIP解压与独立学习副本全部重验，基准/Demo与开发副本一致。无真实LLM或第三方MCP/OAuth；旧回归和网络隔离对照仅本机合成服务。

## 归档与还原

实现Commit `db50a5da4c86adb4d67704554f170e7655ab92ee`，唯一Annotated Tag phase-21固定指向它；最终发布事实另有后续纯文档记录提交，不移动Tag。正式ZIP `/Volumes/move-disk/data/code/mybot-mini-snapshots/phase-21.zip`，SHA256 `9ee8c896ccef8977b6d5cc5aa0cb1dac9fa24bd9c43345bda53e12f64cfc6e48`，166 entries/147 files，CRC/提交SHA/逐文件等于Tag/安全审查通过；工作树同级另有相同脚本默认输出。旧21个Tag/ZIP核对未变。

独立学习目录 `/Users/godblack/.codex/worktrees/phase-21/mybot-mini-learning/phase-21`，由当前工作树restore_phase.sh 21生成，已冻结安装/编译/569全量/四组基准/两种Demo验证，147个文件测试后仍等于Tag。原main仍旧代码，不能在那里运行新能力，不覆盖用户文件来同步。

## 已知限制与下一步

SBPL/sandbox-exec已弃用，当前macOS验证不承诺未来兼容；无Linux/Windows新沙盒。只读命令不等于所有工具只读；host当前用户权限。元数据/祖先目录名称可见，私密路径列表和输出处理不是完整秘密脱敏；模型原参数/结果可能进入持久Session。临时总量为轮询阈值非硬配额，无内存/恶意fork隔离；killpg不能保证脱组后代全清理；asyncio私有transport及最后exec文件系统竞态有兼容/安全边界。固定模型不证明真实模型能力，真实Token/费用未验证。

当前阶段无未完成项，保留独立分支/worktree供审阅。不要重复实现、调旧heldout或移动Tag/覆盖ZIP，不混入用户修改，不自动Push/Merge/Phase22。
