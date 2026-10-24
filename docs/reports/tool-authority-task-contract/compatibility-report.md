# 兼容性与测试迁移

安全默认值的变化是显式迁移：旧 off 模式自动写入改为 read_only；正向旧功能通过 legacy_confirm + 每次批准保留。原测试未删除，原期望值和业务断言保留。新增安全专项独立验证默认拒绝、手工调用拒绝、真正无副作用和显式兼容成功。

|文件|迁移原因与保留行为|
|---|---|
|check_phase / check_session / check_planning / check_persistence|旧写后读、会话配对、成功/失败计划、超时后的副作用保留；仅 Registry 构造显式兼容并提供合成逐次批准|
|check_context|旧有写后上下文裁剪/预算失败保留。20KB 写入超过安全完整审批显示上限，特定用例改用显式原生 Patch add，仍断言写入20000字节、后续预算失败、计划失败、未保存会话；小写入继续走审批兼容|
|check_list_files / check_repository_tools / check_patch_editing / check_command_execution|旧3/7工具集合的正向兼容断言使用显式 legacy 配置；原 Patch 模式互斥、版本/元数据/边界行为断言不变|
|check_mcp / check_mcp_http / check_tool_discovery / check_adaptive_routing|原允许MCP的可见集合、连接清理后本地写入、非互扰行为继续在显式兼容上下文验证；MCP allow/confirm/deny 断言不改|
|compare_tool_discovery|旧工具集合比较显式选择 legacy_confirm 与真实CLI审批提供者；该合成比较没有文件写入，不新增或更改旧排名/任务成功规则|
|evaluation/runner|旧教学评测在隔离临时目录明确选择兼容写入；离线使用合成逐次批准，Live需要原生CLI逐次批准，不自动yes；原 grader/fixture/期望不改|
|evaluation/tool_agent 与 check_routing_confidence|只增加显式 file_access/宿主审批传递；旧 builtin-write 案例配置 legacy_confirm 和合成批准，其实际文件效果/0 MCP/1工具断言不改，Harness 缺省仍只读|
|check_autonomous_coding / check_git_workflow / check_coding_campaign|原“不新增合同 Schema”及冻结10工具集合测试显式 coding_task_contract=false；其他任务仍使用新默认。无新增Undo工具、Git安全和真实性断言保持|
|check_autonomous_coding / check_git_workflow / check_patch_editing / check_command_execution 的 Fake/Spoof注册|模拟第三方结果的宿主调用明确赋 external_side_effect 能力，继续验证结果不能伪造原生Revision、重试或Journal。另有新专项验证未知类型不能靠名称/属性声明获得权限|
|check_runtime_accounting|仅UTF8写入用例改为显式兼容及合成批准，仍验证“中文”写入为6字节；真实资源统计与计数规则不变|

全部原测试断言数量保留。三处把配置构造直接写在 assert 参数中的旧集合断言 AST 会出现新增 file_access 参数；去除这一已披露的配置输入迁移后，原断言 AST 应与基线一致。其余既有断言逐节点比较不变；安全审计记录实际检查结果。

当前教学兼容不意味着任意旧脚本无条件可运行。新写入不自动创建父目录、不接受符号链接/敏感路径/不支持元数据、不允许不完整审批或无Provider；空文件覆盖目前拒绝，原生Patch也没有空锚点插入协议，需要明确宿主操作或以后独立扩展，不能自动绕过。

回归中发现的旧预算 JSON 末尾解析依赖通过调整合同提示位置保留，没有改Controller逻辑/预算或测试解析规则。旧Live结果、冻结Fixture、Judge、历史报告、Phase Tag/ZIP保持原样。
