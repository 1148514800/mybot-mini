# AI_HANDOFF

## 当前目标与状态

codex/repo-map-v1，基线470433685a90aac3dacd0536dddb1f9fbd2332c1。Repo Map v1已实现；13项新增专项，连同Repository/Patch/Tool Authority/Web/Provider Chain共200项相关离线测试通过。Python编译、JS语法及diff检查通过。真实模型请求0，无Canary/冻结/完整Benchmark。

## 实现与权限

mybot/tools/repo_map.py复用RepositoryTool，Git已跟踪文件按需扫描，标准库AST提取顶层函数/类/直接方法及静态import/行号；仓库内目标明确标静态候选/歧义，不声称运行时图或业务语义。最多120文件、512KiB/文件、12KiB含元数据输出；有界名称编码、AST节点/记录/进程限制及截断提示；单文件AST失败不终止。非Python不读正文，私有路径及所有符号链接跳过。RepositoryTool.read_bytes新增可选更严大小限制，默认行为不变。

仅Coding模式原生Registry注册；read_only授权及AgentLoop undo白名单认定原生类型，不自动扫描/增加调用。原search/read/Patch/Receipt/Approval/Provider Chain保留。Web项目区域显式按钮POST /api/repo-map，沿用同源Cookie/CSRF/CSP，固定进程workspace；不构造模型Client，不返回绝对路径，不编辑项目。普通聊天不注册模型工具，用户仍可只读点击查看。

## 验证与限制

新增专项覆盖函数/类/方法/行号、相对导入/歧义、无效AST、私有文件/链接、文件数/大小/输出上限、控制字符、无执行/Index及工作区字节不变、Coding注册、AgentLoop Mock调用/简单消息不扫描、Web按需与鉴权。原关键Patch及权限断言保留，仅更新新增只读工具导致的Registry数量。

地图仅跟踪文件；有限索引/src/sys.path/动态import/重导出无法证明，index_incomplete不能解释成无依赖。每文件是读取时观察，非全库原子快照；沿用原仓库工具路径权限，非恶意并发改写的完整OS沙盒。普通源码命名不做通用秘密识别。详见README和docs/repo-map.md。

## 下一步与保留

本轮提交Push codex/repo-map-v1并核对远程HEAD，不创建Phase/Tag/ZIP。main、旧C01/C02报告/私库/冻结/账本/剩余额度和用户Chrome/Web服务不改动；真实模型验证须另获授权。已存在项目启动--workspace/--check、Provider Chain及原Coding写权限策略继续复用。共享Git的AppleDouble副文件可能产生non-monotonic警告，不操作该共享元数据。
