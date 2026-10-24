# AI_HANDOFF

## 当前目标与状态

Tool Authority & Task Contract 强化已完成实现、专项/完整离线和真实浏览器合成验证。独立分支 codex/tool-authority-task-contract，从指定 fd913d938e4bfcda8a6b892780fa987a62906487 开始；不合 main、不改 Phase Tag/ZIP。当前准备 Implementation 提交；Acceptance 报告和 Push 在下一交付步骤完成。

## 已完成与关键决策

- 默认 coding.file_access=read_only；普通聊天不暴露/执行 write_file。Registry 可信类型/显式宿主能力分类，Schema/execute/MCP Catalog 激活共用权限过滤，手工调用不能绕过。
- 显式 legacy_confirm 与 Patch 互斥，逐次完整内容审批，内部复用原 Patch Preview Receipt/版本/dir-fd/元数据发布检查；不自动建父目录，无法完整安全展示/无Provider/空文件覆盖拒绝。CLI/Web一致，命令/MCP仍是独立权限域。
- coding.task_contract 默认true，仅自主编码任务激活。最多12条、320字/条、输入与累计预算；当前用户精确原文或真实版本化文件读取建立来源，模型建议/未决分开；只追加不可删除或自报PASS。
- 复用原 Controller 的当前Revision和真实测试记录；声明Level1、测试记录关联Level2不证明需求覆盖；独立可信宿主断言才有Level3。无Oracle/提取完整性证明时Task Correctness为unknown。合同不恢复授权，不跨任务恢复；无固定额外模型抽取/评价请求，工具往返仍消耗原预算。
- CLI计数和Web折叠面板展示真实状态；事件不发送私有原文，只发送来源坐标与必要状态，Web从既有脱敏消息还原简述。项目文档需求暂仅显示编号/类别。

## 文件与验证

核心：tools/authority.py、registry.py、file.py、file_approval.py；agent/task_contract.py、loop.py；config/app/Web runtime/approval/静态页；MCP Catalog。三组新增专项、合成/浏览器验收工具；历史依赖隐式写入的测试改为明确兼容配置，原断言保留。设计与完整证据在 docs/reports/tool-authority-task-contract/。

最终 check_phase 44组1448项 + 独立UAT补充79项 = 去重1527项；原1469全部保留，新增58项，无跳过。用户指定Web/Receipt/可靠性/Failover/命令五套单独重跑通过；compileall、JS语法、diff检查通过。A/B真实Patch→Receipt→原生unittest→Revision verified，B未覆盖需求仍unknown且独立断言失败；C CLI/Web文件及Git工作树不变、1次合成请求后拒绝。实际浏览器A/B/C通过，临时服务和页面已关闭。真实API/DeepSeek/GLM/真实语义摘要/付费Judge均0。

Controller、Patch、RunCommand、Seatbelt、Command Approval、Undo、WorkspaceLease、MCP Approval/Manager十个核心文件与基线逐字节相同；729个旧保护资产未变。凭证/禁入路径/大文件检查通过。原main仍有用户 mybot/app.py、workspace/instructions/USER.md 两处未提交修改，未带入新worktree。

## 限制与下一步

精确引用不证明语义提取完整；Level2关联来自模型且覆盖未知。没有日常独立Oracle，不声称真实模型质量或费用改善。legacy/host_confirm无OS隔离，MCP不受Patch保护；Patch仍不解决全部恶意并发或跨文件崩溃原子性。空文件写入与跨轮需求替代尚未支持。

完成Implementation、Acceptance两次提交并按用户授权Push指定分支，核对远程HEAD与干净工作树。不要合main、改旧Live结论/冻结资产、重跑旧T01/T02/T03、复用旧额度或进入下一Phase。
