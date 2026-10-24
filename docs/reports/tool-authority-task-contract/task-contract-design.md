# Task Contract 设计与学习说明

目标：在既有自主编码 Controller 之外记录需求来源和证据状态，避免把指定测试通过误读为所有需求正确。无需新的模型分类请求或常驻 Judge。

mybot/agent/task_contract.py 提供 TaskContract、不可变 Requirement、ContractTool。coding.task_contract 严格布尔，默认 true，但仅 coding.autonomy.enabled 任务注册工具并建立实例；可显式 false 保持旧任务工具集合。普通聊天不建立合同。每个 handle_message 是一个任务，生成新的 task_id；跨轮/Session 不恢复合同或授权。用户在下一任务修改需求时旧 Session 文本保留，但没有跨轮 supersession 自动判定；不允许模型修改当前合同旧条目。

流程：真实用户输入 → TaskContract 只读来源快照 → 模型同一响应提出合同与只读工具 → 宿主精确校验、原子追加 → 原 Patch/Command 执行 → Controller 观察 → 合同读取已产生的测试记录 → CLI/脱敏 Web 呈现。模型没有提交时 established=false、coverage=unknown。

字段包含 requirement_id/text/source_type/reference/category/added_version/added_at；状态及 evidence_refs/current_revision 从宿主视图派生，不接受模型 status 或 PASS。最多 12 条，每条 320 字，输入 16KB，累计需求序列化 9KB，来源最多12个有界节选、测试记录最多32个。模型只可追加 requirements、追加 claims、链接已经存在的 test-N；不提供删除、替换、降级来源或修改硬性要求的入口。重复 ID、伪造引用、无效链接使整批失败，无部分写入。

user_explicit：requirement_text 必须是实际当前用户输入的精确子串，source_reference=current-user；工具不能传入替代用户消息。只能证明该原文确实存在，不能形式证明该句是命令而非用户引用的反例，语义提取仍有局限。

project_documented：仅真正 ReadFileRangeTool 成功结果可产生 document-N；必须带真实完整文件 SHA，校验当前文件版本，需求文本必须在实际返回的行节选中。记录时再查版本；后续版本改变使来源状态退为 unverified。read_file、MCP 文本、模型给出的路径/SHA 都不能建立该来源。内部保存真实路径和 SHA，外发不暴露。

agent_suggestion/unresolved：无可信来源 reference，仅以未验证/待确认显示，不能增加用户明确要求数。所有合同记录仍为 tool-role 任务数据；不会被插入 system 权威指令，压缩摘要也没有权限升级入口。

关键函数：record 原子验证/追加；observe_read 捕获已读文件的节选与版本；observe_test 读取原 Controller 已接纳的真实测试结果；snapshot 按当前 Revision/哈希计算状态；verify_independently 仅宿主执行可信 callable，不是模型工具；public_snapshot 只发送编号/分类/状态/计数与用户来源字符坐标。Web 从已经脱敏显示的当前用户消息本地还原简述（字符长度不匹配时退为编号）；不在事件再次复制私有 Prompt、文件路径、SHA、Receipt 或 nonce。项目文件条目目前显示类别和编号，不复制文档正文。

复现命令（macOS/zsh、Python3.12+、uv）：uv sync --frozen；uv run python mybot/main.py；uv run python -m scripts.check_task_contract；uv run python -m scripts.check_requirement_evidence。浏览器合成入口：uv run python -m scripts.authority_contract_browser --scenario B --port 8884。只会创建临时合成 Client，不构造 SDK 客户端。
