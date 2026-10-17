# AI Handoff

## 当前目标与状态

Phase19 Repository Exploration & Code Search已完成并独立验证，停止等待下一任务，不进入20。成果分支codex/phase-19，worktree `/Users/godblack/.codex/worktrees/phase-19/mybot-mini`；原main仍3461dc7，原工作区app.py/USER.md未提交修改内容哈希不变。未自动合并或Push。

## 实现与架构

coding.enabled严格布尔、未知字段拒绝、默认false，旧Registry仍3工具，显式true加search_code/read_file_range/git_status/git_diff四原生工具。Gateway接线；Coding Workspace须已存在、不bootstrap写入。沿用Tool/ToolResult/Registry/AgentLoop，Loop仅增加私有参数日志遮蔽，MCP/路由/Plan/Context/Session未重构。

repository复用FileTool._resolve，统一敏感路径策略、普通文件/严格UTF8/NUL拒绝/2MiB保护。search用真实rg安全Rust regex或literal、遵守gitignore有界枚举2048文件、50匹配、真实路径/行/UTF8字节列、约16k输出。range闭区间1-based至多200行、约16k、CRLF保持、截断及下一行明确。Git根须在Workspace内，支持nested/worktree；status NUL/XY/rename双路径/200条，截断不称clean；Diff staged/unstaged固定参数/literal路径/300行约24k/不含Untracked。

内部readonly_process仅固定Git/rg argv、可信宿主二进制/最小环境、禁用Git外部helper/filter/fsmonitor/textconv/pager/惰性fetch、5秒整工具预算、读取时字节/记录限额、超时取消回收本次进程组。r1拒绝含等号/空格/引号/非ASCII等歧义可执行过滤器键，防Git -c分割覆盖绕过。不提供模型Shell/Patch/测试执行/自动修复或Git写工具；原write_file仍存在。

## 验证与归档

34项专项、456项全量（旧422+新34）和Phase1/2断言通过，归档修订脚本集成通过。四组旧基准与独立Phase18除耗时/Git元数据逐字段一致。真实合成Git/rg及原AgentLoop Demo：5次固定模拟请求定位src/calculator.py:1 add使用减法，业务文件/Index未变，ID配对；无真实LLM、无第三方MCP/OAuth。APFS与外置磁盘独立安装编译验证，外置学习目录全456项再次通过，四组基准及Demo一致；正式ZIP另行独立解压的34项及Demo通过。

实现230374b，r1安全修复与归档实现6c2747799dfca74c49815fa7351ccabffd5fe342，Annotated Tag phase-19-r1固定指向6c27477。正式ZIP `/Volumes/move-disk/data/code/mybot-mini-snapshots/phase-19-r1.zip`，SHA256 `5b7d8691af0edcd5ff1536044d9cb31ab32cc06fb443bb8acfc9ce84af561e30`，155 entries/136 files，逐文件等于Tag，无._*。学习目录 `/Volumes/move-disk/data/code/mybot-mini-learning/phase-19-r1`，由新worktree脚本 `bash scripts/restore_phase.sh 19 r1`还原；原main旧脚本不支持r1后缀。禁止覆盖已有目录。

初版phase-19/ZIP在归档后发现Git歧义过滤器名漏洞，已被r1取代；按不可覆盖规则保留旧Tag/ZIP/学习目录，不应使用旧版。旧Phase1–18与初版19归档哈希全部未变。最终归档事实由后续纯文档记录提交保存，不能移动Tag重导出。

修改共21文件：8新增（5工具模块、coding_repo_demo、check_repository_tools、phase-19学习文档），13修改（registry/config/app/Loop日志、配置模板、check_phase、4归档脚本、README/索引/本交接）。完整学习说明和文件清单见docs/phases/phase-19.md。

## 已知限制与下一步

仅UTF8/2MiB，2048文件/输出/时间预算影响召回；长单行无字符偏移续读。源码/Diff进入Provider请求与Session，可持久化，无完整秘密脱敏/OS沙盒；信任宿主二进制、Git元数据与非恶意并发文件系统。屏蔽过滤器（含LFS）和全局配置可能导致Git视图与普通Git不同，配置枚举与调用非原子。固定模拟器不代表真实模型理解能力。

保留独立worktree供审阅，原main和用户文件不动。完成后停止，不自动Push/合并/Phase20；不要重做已通过的实现或强制覆盖任何Tag/ZIP。
