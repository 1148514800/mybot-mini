# AI Handoff

## 当前目标与状态

Phase20 Patch-Based Editing已完成：55项专项、511项全量及原断言、编译、归档集成、唯一Tag/完整ZIP与独立还原全部验证通过。停止等待新任务，不进入21、不Push/合并。分支codex/phase-20，工作树 `/Users/godblack/.codex/worktrees/phase-20/mybot-mini`，基线4343ada含Phase19安全修订；原main仍3461dc7，用户app.py/USER.md与原Index哈希不变。

## 实现与架构

- coding.patch_mode默认off，preview/write必须enabled=true；Patch模式真正移除默认原生write_file，保留read/list、四调查工具并加apply_patch。旧Schema/Registry兼容；MCP权限/Discovery/OAuth/路由默认不变。原生Patch不受MCP Approval自动保护。
- range在Patch模式返回完整原始字节SHA256/bytes；结构化update/add，严格Schema、解码前256KiB限额、8文件/16编辑、2MiB文件、24000字符Diff。锚点同一快照唯一且非重叠，字节拼接保护换行/BOM/未选内容；stale不自动换哈希。
- 全量Preflight，默认Dry Run无临时写入；write显式false才同目录stage+备份、重新验证、update原子replace/add no-clobber hardlink、读回验证。错误按条件逆序恢复，校验已发布版本及备份；清理校验临时inode，拒绝删除被替换文件。不确定状态需人工检查，无跨文件崩溃事务保证。
- 复用保守敏感路径，写入拒绝全部相对路径符号链接/隐藏目录/越界/特殊文件/多硬链接。dir_fd/O_NOFOLLOW、fstat/哈希/身份二次校验。保留mode，仅同euid/egid，拒绝ACL/flags/特殊mode/不支持xattrs；Darwin provenance只在stage/backup属性字节一致时允许。
- 原Loop仅私有参数解析前遮蔽、原生Patch解码限额与可信Plan观察；预览不增加编辑证据，无发布的stale/anchor/ambiguous允许重读重试，未知写入失败终止。第三方Tool伪造metadata不能豁免。原Context/Session架构与默认持久化未改。

## 文件与实测

新增patch.py、check_patch_editing.py、phase-20.md；修改config/app/registry/repository/range、Loop/Plan、配置模板、coding_repo_demo/check_phase、README/索引/本交接，共16文件。完整教学、调用链与已知限制见docs/phases/phase-20.md。

55项Patch、34项Phase19、511项全量（456+55）及Phase1/2断言通过；冻结安装、编译mybot/scripts、最终归档集成通过。四组旧基准与4343ada逐字段一致（除计时/Git元数据），Core四模式12/12、Challenge四模式10/10。真实合成Git Demo8次固定模型请求：真实版本→预览→减法改加法→重读→实际Diff；原用户注释、暂存README、未跟踪notes与Index字节均保留。正式ZIP解压和独立restore副本全部重验通过，Demo逐字段一致。没有真实LLM或第三方MCP/OAuth；旧回归只用本机模拟服务，Agent未执行命令/测试。

## 归档

实现Commit `73688daa2118d6236a17e2cd960399aa4ae00401`，唯一Annotated Tag phase-20准确指向它；最终归档事实由后续纯文档提交保存，不移动Tag。正式ZIP `/Volumes/move-disk/data/code/mybot-mini-snapshots/phase-20.zip`，SHA256 `c53f28904e752701844fc0784c218c5ed1c68f4a3dfcf4f379321e0ed85be9dd`，158 entries/139 files，CRC/提交SHA/逐文件等于Tag/敏感内容检查通过。工作树同级另有脚本默认输出的相同ZIP。旧20个Tag/ZIP全部核对未变。

独立学习目录 `/Users/godblack/.codex/worktrees/phase-20/mybot-mini-learning/phase-20`，由当前工作树restore_phase.sh 20生成，已冻结安装/编译/511全量/四组基准/Demo验证。原main的旧脚本/源码尚不含Phase20，不要在那里运行新功能，也不要覆盖用户文件来同步。

## 已知限制与下一步

仅UTF8/现有父目录/保守路径与元数据；最后检查与rename/unlink仍有竞争窗口，不是OS沙盒；回滚不恢复inode/时间戳，断电/崩溃可留部分修改和临时文件。源码/参数/Diff可进入持久Session，private_arguments仅保护Debug。macOS/APFS已实测，Linux兼容分支未实测；固定模型不代表真实模型自主修复能力，真实Token/费用未知。

当前阶段无未完成项，保留独立分支/worktree供审阅。不要重复实现或重调旧heldout，不移动任何旧Tag/覆盖ZIP，不混入原用户修改，不自动Push/Merge/Phase21。
