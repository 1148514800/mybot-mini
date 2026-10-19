# AI_HANDOFF

## 当前目标与状态

Phase24实现、离线验证、学习文档和本地归档完成；真实模型能力未测。分支codex/phase-24，基线dfd3461；不Push/Merge/进入25。原main3461dc7、用户app.py/USER.md、原Index、24旧Tag及旧ZIP保持不变。

## 实现与架构

新增mybot/evaluation/coding_{fixtures,judge,live,metrics,benchmark}.py、3个评测/演示/专项脚本、12任务数据集。复用原Loop/Controller/Registry/Patch/Command/Journal；原生Tool Schema未改。每次任务独立Git目录，Agent不接触Hidden/Reference；结束后Judge新副本+可信测试+真实Seatbelt评分。默认离线，关闭MCP/Skills/Session持久化/Undo。报告只存元数据，独占写入。

Live需--live与--confirm-api-cost、有效凭证、TTY、真实沙盒；SDK重试0，每条模型命令沿用原逐次审批。请求/输出/单任务/全局时间与显式价格估算预算齐全；未知Usage/成本保留null，错误脱敏。本阶段无真实LLM或API费用。

## 验证与归档

109新专项+750旧测试=859；Phase19～23专项34/55/58/80/101、审批25通过。12任务各公开2/隐藏4，全部Buggy隐藏失败，Reference公开24/隐藏48通过。四旧基准除六个计时/Git字段与Phase23相同。无修复离线12/12完整评分、0修复，能力率/Token/费用null；Demo正确修复/公开过拟合/口头伪造/评分故障区分正确。

实现fafab78、修正178859f；先独立ZIP-only还原全套通过，再添加archive-ready。归档源`3f53b0562c22ce3727d9ffe403880be74dbbd5e1`；annotated phase-24对象`43c325fe77fed6d48ef9cc0844a957e742c272e7`。正式ZIP`/Volumes/move-disk/data/code/mybot-mini-snapshots/phase-24.zip`，SHA256`3c69bb4eb29d982f3f8a9b1c1ea9fe968e098f1e58d3d5a04b8ca7a3fc5f8e09`，278文件逐字节与Tag一致。

正式ZIP独立APFS解压`/var/folders/7p/n7p6_hdd08j48k1kbg6kjnvh0000gn/T/mybot-phase24-official-zip-erbp3ik2/source`及restore目录`/Users/godblack/.codex/worktrees/phase-24/mybot-mini-learning/phase-24`均冻结安装、编译、859全量/四基准/12离线/四Demo通过；源文件哈希未变。归档后仅补文档记录，未移动Tag。完整学习与命令见docs/phases/phase-24.md。

## 已知限制与下一步

真实Provider兼容性、模型能力/稳定性/费用尚未实测；Python同进程测试防作弊不是形式化保证，估算费用不是账单硬上限，Seed只固定任务顺序。只有用户另行明确授权后才执行付费Live；当前停止在Phase24。不重复实现、不改旧750断言、不将离线策略当LLM成绩。Phase24正式Tag/ZIP已存在，禁止覆盖或移动。
