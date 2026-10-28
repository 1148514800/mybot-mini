# AI_HANDOFF

## 当前目标与状态

codex/repo-map-scoped-v2，基线601d2d9fd65f0de477a0abcef5d9ea9542c32583。Repo Map v2目录范围开发完成；新增6项，地图专项19项；连同Repository/Patch/Tool Authority/Web相关专项共187项通过。真实模型请求0，无Canary/冻结/完整Benchmark。

## 实现与权限

repo_map新增可选path，默认.，max_files仍为1–120。仓库相对目录在Git ls-files枚举阶段限定，先筛范围后应用数量/输出上限；复用RepositoryTool原GIT_LITERAL_PATHSPECS=1机制，目录名不解释为通配符。拒绝绝对路径、..、符号链接目录、受保护路径、非目录；不扩大workspace权限。新增scope字段，其余原调用及结构保持。有限索引只含本次目录内的已枚举文件，范围外import保持external_or_unresolved，明确未确认而非不存在依赖。

Web弹窗新增默认.的目录输入与查看按钮，打开不扫描，显式提交才读取，可重复换目录；返回范围/数量/截断状态。原POST Cookie/CSRF/CSP及固定进程workspace不变，不构造模型Client。工具仍只在Coding模式注册，原AST、隐私规则、120文件/512KiB/12KiB上限保持。只修改地图、其Web接口/静态页面和相关测试文档；AgentLoop主体、Provider Chain、Patch/Receipt、RunCommand、WebApproval、WorkspaceLease及权限不变。

## 验证与限制

新增：默认根兼容、Git枚举先范围（140个前置文件后仍定位目标）、目录前缀/字面量/规范化、非法/私有/链接目录拒绝、跨范围import未确认、范围内隐私/无执行/文件与Index字节不变。Web测试扩展输入表单、目录过滤、再次查询及非法范围拒绝，保留原鉴权/无自动扫描/无Provider断言。Python编译、JS语法和diff检查通过。

地图仅跟踪文件，scope为仓库相对目录；有限索引不证明动态导入、sys.path、src布局或重导出。index_incomplete为false也不证明范围外完整。每文件是读取时观察，非全库原子快照；沿用原路径保护，不是恶意并发改写的完整OS沙盒或通用源码秘密检测器。详见README和docs/repo-map.md。

## 下一步与保留

提交并Push codex/repo-map-scoped-v2，核对远程HEAD。不创建Phase/Tag/ZIP，不改main/旧C01/C02报告/冻结/账本/额度，不操作用户Chrome或旧服务。未来真实模型验证须另获授权。共享Git AppleDouble可产生non-monotonic警告，本轮未操作其共享元数据。
