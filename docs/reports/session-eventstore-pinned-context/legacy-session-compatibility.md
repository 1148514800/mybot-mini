# 后端配置与旧Session兼容

在原config/config.json的session中选择一个后端，不要提交真实配置：

```json
{"session":{"backend":"event_sqlite","persist":false,"max_turns":6,"event_path":"~/.mybot-mini/events.sqlite3","event_limits":{"max_bytes":67108864,"max_events":50000,"max_payload_bytes":65536}}}
```

默认省略backend且persist=false为memory；省略backend且persist=true保持原legacy_json。可显式backend=legacy_json启用旧CLI JSON；event_sqlite/memory与persist=true冲突并拒绝，避免两个写者。原session.path仍由旧模式使用。SessionStore模块未修改，不自动读取/覆盖/迁移JSON；没有迁移命令。切换后端前自行备份，旧文件保持原样。

| 后端 | CLI | Web | Pin跨重启 |
|---|---|---|---|
| memory（默认） | 近期Session+进程内event engine | 独立进程内Conversation | 否 |
| legacy_json | 原版本化JSON完整近期轮次 | 仍memory，不导入CLI文件 | 否；JSON不新增Pin字段 |
| event_sqlite | SQLite历史与安全恢复 | SQLite列表、标题、聊天、安全状态 | 是 |

CLI/Web共用相同engine和事件合同，namespace分别cli/web+workspace路径hash；同workspace不自动混合会话。同DB中未知副作用只共享安全屏障。默认CLI恢复最新session，`/sessions`列出、`/session <id>`切换、`/session new`新建；旧JSON不支持这些切换，避免覆盖原快照。

`/history [before_sequence]`输出有界消息及真实message id（创建Pin用）；`/pins`查看。`/delete-session confirm <session_id>`真实删除event engine记录；在legacy_json时这不删除旧JSON。旧JSON的`/clear`保持原清盘行为；SQLite的`/clear`只清模型上下文并保留聊天与Pin，删除请显式delete。memory退出全部丢失，不承诺审计持久性。

macOS运行：`uv sync --frozen`，CLI `uv run python mybot/main.py`，Web `uv run python -m mybot.web --port 8765`。正式入口发送消息会使用真实模型；本专题只通过显式SyntheticClient fixture离线验证，未使用生产入口发真实请求。
