# 安全审计

审计口径：以 fd913d9 代码、当前 tracked/new 内容及真实执行为依据。基线旧 WriteFileTool 从其 Git blob 在隔离临时目录复现普通构造实际写入成功；没有复现工作区逃逸或系统提权。因此问题定性为“写入权限策略与安全保证不一致”。

统一门仅信任宿主精确类型映射/注册参数；未知类型没有隐式能力，工具名、description、结果或模型参数不能授权。原生直接写默认关闭，显式兼容必须有单次完整审批；Native Patch 与它互斥。调用不可用工具立即拒绝，无后续模型修复请求。

新增20项权限测试验证默认/手工调用拒绝、显式兼容、无Provider/敏感或超大审批拒绝、取消、元数据、符号链接、文件/父目录在审批期间变化、Preview不写/Receipt单次、MCP deny无法激活、独立外部权限域，以及真实CLI/Web相同拒绝。既有62项命令与53项Receipt、Patch/Git/Undo/Seatbelt等回归负责更全面的原安全边界。本轮没有将它们简化或放宽。

729个既有保护资产（报告、Phase资料、配置模板、评测数据、Fixture/Judge/冻结清单）与基线字节比较无变更。Controller、Patch、RunCommand、macOS Sandbox、Command Approval、Undo/Undo Approval、WorkspaceLease、MCP Approval/Manager这10个核心文件逐字节一致。只有Catalog添加统一权限过滤，MCP原确认逻辑未改。

全部拟交付文件检查禁止路径、大小及真实私有配置中凭证的精确匹配；没有匹配、没有禁入路径或不必要大文件。扫描不打印真实值。最终扫描文件数和断言迁移结果见 offline-validation.json。没有提交config/config.json、.env、.venv、Session历史、AppleDouble、原始私有Prompt、Receipt、nonce或主机绝对路径到新报告。截图仅来自本轮临时合成输入和最终面板，不含审批详情。

Web合同事件只包含编号/类别/状态/计数/版本和用户来源的字符坐标；浏览器从本页已经脱敏的消息恢复简述，不能因事件另取私有原文。私有引用和文件版本保存在当前任务宿主内存中，不恢复授权。独立断言函数/隐藏内容不进Agent上下文，引用为随机不透明标识。

三个最终浏览器服务在完成任务、关闭页面后正常执行生命周期清理，使用Ctrl-C退出（进程130）；无正式服务替换。首次B试验重启时旧SSE连接被Uvicorn超时取消，记录为初次测试清理插曲；该时任务已完成，最终B重新在独立临时服务验收通过，未复用执行状态或授权。所有本轮端口在交付前检查关闭。

有限并发竞态用例安全拒绝，不承诺防御所有恶意并发。host_confirm/legacy没有OS级隔离；MCP仍为独立外部能力，不能因统一Registry而称所有副作用受Patch保护。详见 remaining-risks.md。
