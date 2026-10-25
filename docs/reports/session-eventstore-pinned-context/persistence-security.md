# 持久化安全

默认 memory，不建磁盘DB。显式 event_sqlite 后，普通聊天和Pin以**本地明文**保存；不是加密备份，不提供完整模型请求回放。敏感内容仍不应输入聊天。此版本目标为本地单用户，不能保护同UID恶意程序或已被读取的屏幕/备份。

建议 macOS APFS 的 `~/.mybot-mini/events.sqlite3`，不能放在workspace内。逐级 O_NOFOLLOW/目录fd验证，祖先所有权必须 root或当前UID，最终目录当前UID且无组/其他访问位（新建0700），DB为当前UID普通单链接文件且私有（新建0600）。每次连接复查inode、目录与SQLite sidecar安全属性，拒绝symlink、不明owner、hardlink、权限扩大和替换。ExFAT如果不能验证POSIX私有权限就拒绝，不降低要求；建议用户主目录。跨检查/SQLite打开的同UID竞争仍有残余风险。

SQLite使用 BEGIN IMMEDIATE、synchronous=FULL、DELETE journal、foreign_keys、secure_delete、temp_store=MEMORY、trusted_schema=OFF、max_page_count；新库创建后fsync文件和目录。已有库先只读核验header、版本和integrity，再核对事件规范hash/连续序列及消息投影；异常不覆盖原库。若SQLite明确报告SQLITE_READONLY_ROLLBACK，只在再次核对私有路径、原始header的application_id/user_version均为本实现v1后，允许SQLite自身锁定并回滚hot journal，再完整只读审查。不会自行删journal或重建库；陌生库及其journal逐字节保留。该恢复遵循[SQLite原生hot-journal机制](https://www.sqlite.org/lockingv3.html#dealing_with_hot_journals)。FULL依赖操作系统/存储实现，不保证硬件永不丢失数据。

新增事件不保存工具参数/结果、完整Patch、SDK异常、审批对象、nonce、Receipt、完整模型请求、独立Judge条件。tool事件只白名单名称/布尔与effect；model失败只固定reason。普通文本替换已配置主/备API Key和显式MCP token_env值，并过滤凭证标记、64hex能力、常见私有绝对路径；不把脱敏器当通用数据分类器。未知格式的秘密可能仍在自由文本中，用户需要自行避免输入。API错误只返回通用storage_failed；浏览器仍受原Host/Origin/cookie/CSRF/CSP限制。

删除：明确确认后 DELETE sessions，由外键级联删除events/messages/turns/tools/pins，secure_delete尽可能清理本库页。测试验证应用404、重开库无记录、合成sentinel不在DB字节中。清上下文只是追加context.cleared，保留聊天和Pins。执行未确认会话先人工检查/复核，禁止通过删除绕过安全状态。

不能承诺不可恢复物理擦除：SQLite日志、先前备份、APFS快照、SSD wear-leveling、交换区、崩溃现场及外部副作用文件可能残留。应用不管理备份或OS快照；需要用户按其介质/备份策略处理。删除不撤销已经发生的命令或文件修改。
