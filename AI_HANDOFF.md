# AI Handoff

## 当前目标与状态

Phase20 Patch-Based Editing实现已完成，55项专项、511项全量及编译通过，待提交和独立归档；未标记阶段完成。独立分支codex/phase-20，APFS工作树 `/Users/godblack/.codex/worktrees/phase-20/mybot-mini`，基线4343ada（包含Phase19安全修订6c27477）。原main仍3461dc7，原用户app.py/USER.md及Index未参与修改；不合并、不Push、不进入21。

## 实现与架构

- coding.patch_mode默认off，preview/write必须enabled=true；显式关键字接线，Patch模式从原生Registry真正移除write_file，保留read/list和四调查工具并加apply_patch。独立MCP权限不受此开关限制，原生Patch不是MCP Approval。
- read_file_range在Patch模式返回完整原始字节file_sha256/file_bytes，off保留旧Schema/元数据。结构化update/add，严格Schema、256KiB参数、8文件/16编辑、2MiB文件、24000字符Diff；锚点在同一快照唯一非重叠匹配，字节拼接保护换行/BOM/未选内容。
- 全量Preflight，默认Dry Run无临时写入；write显式false才同目录stage+备份、重新验证、update原子replace/add原子no-clobber hardlink发布、读回验证。错误条件恢复，核对已发布inode/内容/元数据和备份；清理只删除本工具inode，拒绝删除被替换临时文件。无跨文件崩溃原子性/事务日志/OS沙盒。
- 复用RepositoryTool保守敏感路径，新增逐级dir_fd/O_NOFOLLOW、普通文件/单硬链接/哈希/stat验证。保留mode，仅同euid/egid；拒绝ACL/flags/特殊mode/不支持xattrs。Darwin系统provenance仅在stage/backup属性字节一致时允许；其他系统操作不支持时失败关闭。
- 原AgentLoop仅增加私有参数解析前遮蔽、原生Patch解码前限额和可信Plan观察；预览无编辑证据，无发布的stale/anchor/ambiguous可重读重试，未知写入/回滚冲突终止。第三方Tool伪造metadata不能豁免。Context/Session/MCP/OAuth/路由未重构。

## 文件与实测

新增patch.py、check_patch_editing.py、phase-20.md；修改config/app/registry/repository/range、Loop/Plan、配置模板、coding_repo_demo/check_phase、README/阶段索引/本交接。完整教学与边界见docs/phases/phase-20.md。

55项专项、511项全量（456+55）及Phase1/2原断言通过，编译/归档脚本集成通过；含实际ACL/xattr、换行/权限、预览无写入、多文件故障恢复、备份篡改/临时文件替换、原Loop/Plan/Session/日志与Context。Phase19的34项通过。编辑Demo8次固定模型请求：真实哈希→预览→将减法改为加法→重读→真实Git Diff；原注释/暂存README/未跟踪notes/Index均保留。无Agent命令或测试执行。四组旧基准与4343ada逐字段相同（除计时/Git元数据），Core四模式12/12、Challenge四模式10/10。未调用真实LLM、第三方MCP/OAuth；旧回归用本机模拟服务。

## 剩余工作与限制

代码测试已完成，接下来提交含学习文档的阶段Commit（archive-ready已标记）。从干净提交save_phase.sh 20，核实输出位置后独占复制到正式快照目录，ZIP独立冻结安装/编译/全量回归/旧基准；restore到独立目录并验证，最后记录归档Commit。phase-20 Tag/ZIP开始时均不存在，旧20个Tag/ZIP指纹已存/tmp用于最终核对，不覆盖任何历史。

限UTF8/现有父目录/保守路径和元数据；最后检查与rename/unlink仍有竞争窗口；回滚不恢复inode/时间戳，断电/崩溃可留部分修改和临时文件。源码/参数/Diff可能进入持久Session，private_arguments只保护Debug。固定模拟器不证明真实模型能力。不要重做已通过机制，不混入原用户修改，不自动Push/Merge/Phase21。
