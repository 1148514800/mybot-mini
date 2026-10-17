# AI Handoff

## 当前目标与状态

Phase19 Repository Exploration & Code Search在独立worktree /Users/godblack/.codex/worktrees/phase-19/mybot-mini、分支codex/phase-19开发，基线3461dc7（Phase18已推送）。原 /Volumes/move-disk/data/code/mybot-mini 的main/app.py/USER.md保持原状，不合并、不Push、不进入20。初版230374b已有phase-19 Tag/ZIP，原455项通过但归档后发现Git过滤器名含=可绕过-c覆盖（已实际复现执行marker）。修复及34项专项/456全量与修订脚本集成已通过，待r1提交和独立归档；原Tag/ZIP不移动覆盖，修复版另归档phase-19-r1。原归档不作为最终交付。

## 实现与决策

coding.enabled严格布尔/未知字段检查，默认false；Registry旧调用仍3文件工具，显式true加4原生只读工具。Gateway传开关；Coding模式要求已存在Workspace、不bootstrap写instructions，默认false仍旧初始化。AgentLoop只加2行私有参数日志遮蔽，循环/Plan/Context/Session/MCP/权限未改。

repository.py复用FileTool._resolve并加统一私有路径策略/2MiB/普通文件/严格UTF8/NUL拒绝；range最多200闭区间行、约16k结果，CRLF保留，部分行与续读元数据明确。search两阶段rg：先遵守gitignore有界枚举2048文件，再fnmatch筛选并用默认Rust regex/literal/JSON真实搜索；50匹配、500字单条、约16k结果，UTF8字节列，无Shell/PCRE2/配置注入。

Git本地根须在Workspace内，支持nested/worktree、不使用父目录仓库；status NUL/XY/rename双路径，200条/约45k，truncated不称clean。diff固定staged/unstaged、literal pathspec、无ext-diff/textconv/pager/rename检测/子模块，先枚举允许修改路径，再读300行/约24k Diff，明确不含Untracked。最小环境关闭宿主配置/目标重定向/锁/惰性fetch/replace；固定关闭fsmonitor/hooks，动态屏蔽本地filter clean/smudge/process，r1严格拒绝含=、空格、引号等不能安全放入-c的filter键，防只读Git执行脚本。

readonly_process仅内部Git/rg固定argv与可信宿主位置，真实读取时限stdout/stderr/记录，整个工具5秒，取消/超限回收本次进程组；宿主拒绝组信号时仅kill自有子进程，测试证明无关进程不受影响。不向模型开放run_command。

## 文件与测试

新增5工具模块repository/readonly_process/search_code/read_file_range/git_tools、coding_repo_demo、check_repository_tools、phase-19学习文档；修改registry/config/app/debug分支、配置模板、check_phase及README/索引/本交接。旧文件工具、检索器/路由/Gold/依赖均未改。

33项专项通过，真实合成Git/rg和原AgentLoop Demo用5次模拟请求定位src/calculator.py:1 add的减法Bug，实际状态/Diff核对，业务文件与Index未变、调用ID配对。未运行fixture测试或修复Bug，无真实API、无第三方MCP。四份旧基准与独立Phase18逐字段一致（除计时/Git元数据）。

## 限制与下一步

源码/Diff会进入Provider请求及Session，持久化开启可落盘，没有完整秘密脱敏或OS沙盒。父目录并发替换/硬链接、可信Git元数据/宿主二进制需信任；只支持UTF8、长单行尾部无字符偏移续读，有限枚举/结果/时间需据truncated缩小范围。原write_file仍在，不是整个Agent只读。初版旧33/455回归及旧基准兼容通过；安全复核失败已修复，当前34/456及归档修订集成通过。只提交r1修复、同等不可覆盖的可选rN归档脚本支持及学习文档。保留原phase-19/ZIP事实，另建phase-19-r1修订归档与学习目录，不改写历史。保持原main/用户文件不变，不覆盖旧18个Tag/ZIP，不自动Push或进入20。
