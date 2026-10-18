# AI Handoff

## 当前目标与状态

Phase21 Terminal Execution/Approval/macOS Sandbox已实现，58项命令专项、55项Patch、34项Repository、25项MCP Approval与编译通过；最终全量569=511+58及原断言通过，待实现提交和独立归档，未标记阶段完成。独立分支codex/phase-21、工作树 `/Users/godblack/.codex/worktrees/phase-21/mybot-mini`，基线已推送的Phase20 db50c67（Tag73688da）；原main仍3461dc7，用户app.py/USER.md和Index保留。不自动Push/Merge/Phase22。

## 实现与架构

- coding.command默认off/30秒/32768字节，严格类型/字段；非off需enabled，host_confirm还需patch_mode=write。显式Registry/Gateway关键字接线，原Schema默认不变、Patch-only保留。CLI独立命令Provider，真正单次ApprovalDecision.APPROVE，非TTY/无Provider/异常/敏感或不能完整展示的参数拒绝；不缓存授权，不伪装MCP。
- 共享arguments解析器（Patch保留限额），原生run_command解码前16KiB限制/32 argv/每项2048字符/总8192 UTF8，拒绝重复键、非有限数、深层对象/环境/策略/stdin等。固定可信Python/base或校验项目venv；uv仅固定run --no-sync python形态，实际增加离线/无配置/固定解释器，完整有效argv审批。cwd固定fd+审批后与自检后重核，运行时指纹冻结。
- command_process独立于Phase19 runner：可信-I/-S资源引导器、CLOEXEC exec握手、最小环境/专属HOME/TMP/cache，双流合计有界输出，wall/CPU/文件/FD限制，临时32MiB/512项监测，独立进程组、有限清理/取消重抛、detach持管道有界关闭。输出编码/控制/已知路径与凭证标记处理。
- macos_readonly真实sandbox-exec deny-first策略，代码/具体运行时只读、只许专属临时目录写、网络/Mach禁止、Workspace/Index不能写、已知私密路径不能读、hardlink与process-info禁止、sysctl窄许可含vm.pagesize兼容项。每次批准后13项真实合成隔离探针（含可达本机网络对照/别名/子进程/私密文件）必须通过才启动项目命令，失败绝不转宿主。
- 原Loop/Plan只增加真实RunCommandTool类型的非零完成反馈：success=false但completed/command_nonzero=true保留in_progress、清除verified，不标safe_to_retry或自动重复。审批/沙盒/超时/不确定停止批次并配齐ID；MCP先拒绝再排队command仍保留原文案。MCP/路由/OAuth/Context/Session架构默认未改。

## 文件与实测

新增arguments/command_config/command_approval/command_process/macos_sandbox/run_command六模块、check_command_execution.py和phase-21.md；修改config/app/registry/Patch解析/Loop/Plan、配置模板、coding_repo_demo/check_phase、README/索引/本交接，共20文件。学习文档含完整20文件表、核心函数和调用图。

macOS26.6.2、Python3.12.14、uv0.12.10已真实验证58专项及13项沙盒门控；uv/Python可运行，父进程参数读取有宿主对照并被沙盒拒绝。真实原Loop演示12个固定模型请求/2次合成单次审批：unittest先exit1（-1!=5），实际SHA→Patch预览/写入→同一测试exit0、1项通过；两次Seatbelt=true，host版明确false。注释/暂存README/未跟踪notes/Index保留。四组旧基准与Phase20 db50c67除计时/Git元数据逐字段一致。没有真实LLM或第三方MCP/OAuth；既有测试只用本机模拟服务。

## 剩余工作

最终冻结版全量569项及Phase1/2原断言、编译通过；58/55/34/25专项通过。四组旧基准与db50c67除计时/Git元数据逐字段一致。归档脚本集成已通过，正式归档时再用确切提交验证。学习文档已标记archive-ready，索引待创建Tag。

接下来检查diff、提交本阶段实现，从干净Commit运行save_phase.sh 21；核实默认工作树同级ZIP位置，独占复制正式 `/Volumes/move-disk/data/code/mybot-mini-snapshots/phase-21.zip`。ZIP独立APFS解压/冻结安装/编译/全量/基准/Demo，restore到独立学习目录重验，最后纯文档归档记录Commit。phase-21 Tag/ZIP/学习目录开始时均不存在；旧21个Tag/ZIP指纹存/tmp/phase21-old-{tags.txt,zips.json}，不能覆盖历史。原main app/USER/Index SHA已核对未变。比较助手/tmp/phase21-compare.py、基线/tmp/phase21-baseline-0-*.json；演示/tmp/phase21-demo-{sandbox,host}.json，仅临时报告不提交。


## 已知限制

SBPL/sandbox-exec已弃用，当前macOS验证不承诺未来兼容；Linux/Windows无新沙盒。只读命令不等于全部工具只读；host模式当前用户权限、无OS隔离。元数据/祖先目录名称可见，私密路径列表不是完整秘密分类器；原始模型参数和输出可能进入持久Session，Debug遮蔽不保证全链脱敏。临时总预算是轮询阈值非硬磁盘配额，无内存/恶意fork隔离；killpg不保证脱组后代全清理，私有asyncio transport接口有兼容风险。真实模型自主修复、Token/费用未验证。不得把这些限制描述为已经解决。
