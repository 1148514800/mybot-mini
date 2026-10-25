# 安全与历史资产审计

本专题只修改授权的独立worktree/分支。原main HEAD仍为8c1a049904f9544fc5eaeb53c06f6712e43ea320；用户原有mybot/app.py与workspace/instructions/USER.md两处修改仍在原目录，未带入本分支。指定基线核对2b8b2aa29a7adab5909730e85dc678ad60eb2a69。

提交前对965个原跟踪文件及新增交付文件检查禁止路径、文件类型/体积，并在内存中读取本地真实配置中的凭证值做全文件字节匹配（不输出值、不复制配置）；匹配0。新增实现/测试/文档另作内容审查：只用合成消息、临时独立workspace和显式fixture，不含真实会话DB、有效Receipt/nonce、SDK异常或隐藏Judge条件。合成测试里的标记不是有效凭证。截图逐张核对，不保存审批弹窗原文。

- 禁止路径/秘密匹配/不必要>5MiB文件：0；无.env、.venv、真实config.json、.mybot_state、数据库、ZIP、缓存、临时文件或AppleDouble进入交付。
- 737个既有保护资产（阶段文档、历史报告等）与基线逐字节相同；历史UAT/冻结评分/Live Attempt未改。
- 52份原check专项文件未改；check_phase只增加5个新suite入口，没有删测试或弱化断言。
- 14个核心文件与基线逐字节相同：Controller、TaskContract、Patch、RunCommand、command_process、Command Approval、Undo Approval、WorkspaceLease、MCP Approval/Manager、ContextCompactor、TokenCounter、RuntimeAccounting、旧SessionStore。
- Registry新增权限门后的持久化observer，存储失败在dispatch前向上传播；不绕过原权限/审批。AgentLoop仅接入生命周期与投影，Web保留原清理屏障。原生工具安全测试和完整离线回归结果另见offline-validation.json。
- 所有Phase Tag只读取，没有创建/移动；既有ZIP只做只读hash inventory，未覆盖或新归档。此专题不是编号Phase，没有phase26学习ZIP。
- 临时浏览器、自己启动的服务和已知合成命令子进程均清理；仅push授权专题分支，不合main、不force push。

权限/删除/本地攻击者剩余边界见persistence-security.md和remaining-risks.md。此审计是明确范围内的代码/内容/回归检查，不声称形式化安全证明。
