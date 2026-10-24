# 写入与副作用入口审计

基线 fd913d938e4bfcda8a6b892780fa987a62906487。计数口径：**5 类 Agent 可达修改/副作用入口**：WriteFileTool、ApplyPatchTool、RunCommandTool、第三方 MCP、宿主 Undo。CLI/Web 为两条入口通道，不重复计数；Skills、只读 Git 工具不是新增写入原语。MCP 实际工具数随本地配置变化，不能用类数冒充实例数。

基线复现：build_default_tool_registry(workspace) 在 patch_mode=off 时注册 write_file；WriteFileTool.execute 解析路径后 mkdir/write_text，普通合成调用实际创建文件。问题定性为 **写入权限策略与安全保证不一致**。未复现工作区逃逸或系统提权，不作此宣称。

|入口|调用与暴露/可执行|审批与 OS|路径/版本/元数据|取消、失败与证据|
|---|---|---|---|---|
|旧 write_file|普通模型在 off 模式默认可见可写|无审批；无 OS 隔离|resolve 工作区检查；无 Patch SHA、dir-fd、Receipt、发布元数据保证|异常 ToolResult；成功输出字节数，非 Revision 证据|
|新 write_file|仅显式 legacy_confirm；Registry 再校验，需可用审批 Provider|每次完整替换内容确认；无 OS 隔离|限制相对路径/敏感路径/符号链接；复用 Patch SHA、元数据、dir-fd、内部 Preview Receipt；不创建缺失父目录|取消先于提交无写入；审批间内容或父目录变化拒绝；提交沿用原发布/恢复/不确定结果|
|apply_patch|coding enabled + preview/write；无旧直接写入口|模式是显式授权；Preview/Receipt 模型提交保持原协议；无 OS 隔离|原 SHA、dir-fd、元数据、Receipt 单次消费、TTL/范围、阶段发布检查不改|原失败/回滚冲突/不确定保留；Controller 观察真实原生结果|
|run_command|显式命令模式才注册；统一门只负责分类|原单次确认；macos_readonly 原 Seatbelt；host_confirm **无 OS 隔离**|argv/cwd/固定运行时的原检查；不受 Patch 内容协议保护|原进程停止/超时/输出限制、取消及不确定；原 Controller Revision 测试证据|
|MCP|manager allowlist + allow/confirm/deny；Catalog/Registry 双重过滤|原确认机制；远端/stdio 具有自己的系统权限，无本地 Patch 沙箱保证|不把未知 MCP 视为只读，也不纳入原生文件许可；本地文件版本/元数据并非通用保证|原 owner task/连接清理/审批/审计；不采信其返回文本为原生测试证据|
|Undo|CLI 宿主 /undo，非模型工具；Web 原版本明确不支持|原逐次 Undo 确认；无新 OS 隔离|原胶囊、路径、版本、元数据、Git index 检查及 Patch 发布基础|原冲突/部分失败/消费；使旧 Revision 与本轮合同证据失效|

Skills 仅加载有界说明和参考文件，再调用同一 Registry；文本不能新增工具权限。git_status/git_diff 为只读进程包装；没有原生 Git commit/reset 写工具。命令或 MCP 执行 Git 属其独立权限域。

宿主附属写入另列 **4 类**：workspace.init_workspace 首次创建引导文件；SessionStore 保存/清空历史；WorkspaceLease 外部锁；评测/演示程序构建临时 Fixture、输出报告或显式保留产物。它们不由模型文件调用直接选路径，不宣称统一 Registry 使整个进程只读。已检查 mybot 下全部 write_text/write_bytes/open/replace/unlink/mkdir 调用位置；本基线不含 main 后续加入的 Web 设置写配置功能。

CLI mybot/app.py 与 Web runtime.py 传入同一 file_access 配置；均通过 AgentLoop → ToolRegistry.execute。Undo 是保持原宿主专用 gate 的例外；它没有被虚假包装成模型 Schema。WorkspaceLease、工具取消/不确定清理流程保持。
