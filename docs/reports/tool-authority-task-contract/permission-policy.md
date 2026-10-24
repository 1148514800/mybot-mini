# 权限策略

原生精确类型由宿主 authority.native_capability 分类：read_only、workspace_mutation、command_execution、external_side_effect、metadata_only。自定义工具须由可信注册调用显式声明 capability；未知类型/子类/名称冒充默认不可见且不可执行。模型参数、description、工具返回 metadata 均不参与授权。可信 Python 代码仍能注册能力；这不是防御恶意宿主插件的进程沙箱。

默认 coding.file_access=read_only。未开启 Coding 的普通聊天只注册 read_file/list_files，再按配置增加计划/技能/发现元数据工具。read_only 表示关闭原生普通文件修改，并不承诺 OS 只读或外部 MCP 无副作用。命令和 MCP 需要各自显式配置与审批。

显式原生编码：coding.enabled=true、patch_mode=write、preview_receipt=true，建议保持 file_access=read_only（它仅控制 legacy）。工作流为 read_file_range → apply_patch Preview → Receipt Commit。preview 模式同样注册 Patch，但工具自身拒绝写入；未知/禁用工具通过手工调用也不能绕过 Registry。

兼容：file_access=legacy_confirm 仅允许 patch_mode=off，严格拒绝未知值、非字符串、与 Patch 同时启用。无审批 Provider 不显示兼容工具且拒绝执行；非交互 CLI Provider 默认拒绝。参数不可额外提供 enabled/approval 或授权对象。

get_definitions 与 execute 共用 permitted；MCP Catalog 构造和再次 activate 也检查，动态发现不能恢复被拒绝能力。现有 request-visible 快照继续阻止同批新激活的 MCP 调用。拒绝返回 authority_denied、permission_denied、executed=false，并停止本轮后续工具与模型补救请求。

命令审批、macOS Seatbelt、MCP allow/confirm/deny、Receipt、WorkspaceLease 分别保留原安全实现；统一分类不使这些域获得可互换的写许可。
