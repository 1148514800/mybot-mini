# 自动核查安全审计

- 只用当前ps/lsof确认PID、父子关系、UID、启动命令、启动时间、cwd和端口；不把历史PID当授权对象。没有kill、pkill、SIGKILL、SIGTERM或锁删除。
- 原Chrome授权标签通过浏览器工具认领；read-only DOM evaluate仅选择服务标题、会话数量、消息元素children.length、状态、审批/停止/清理提示和dialog开关。不读取聊天节点正文、聊天标题、输入文本、设置值、cookie、CSRF或认证字段。消息正文和密钥没有进入工具输出、报告或Git。
- 当前memory服务含消息，无法证明其无需保留；按用户第6项及fail-closed要求保留。设置dialog打开是观察事实，不据此臆测有/无已修改配置。另一个worktree的launcher也没有擅自终止。
- 未修改原用户页面/会话/服务；不创建未授权备份、不清空或导出数据。没有截图，因为当前页面可能含私聊且没有获授权读取正文。
- 原verify在调查开始与报告生成时成功；同一冻结批次、配置字节、source hash、两个DB inode及workspace指纹保持。Ledger仅只读检查，无case/reservation/halt；event空库完整性正常。
- 本次只新增独立recovery-execution-01报告与更新AI_HANDOFF，不改旧BLOCKED、OFFLINE、Preregistration、生产源码或原脚本，不新增测试、prepare/freeze、账本、Tag、ZIP或main改动。
- 在同分支提交/Push前审查diff、JSON哈希和已配置凭证的字节匹配；不提交SQLite、真实配置、Key、Cookie、CSRF、Receipt、nonce或聊天导出。
