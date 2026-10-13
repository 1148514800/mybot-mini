# AI Handoff

## 当前状态

Phase 05 Session JSON 持久化已实现并离线验证，待本次提交、phase-05 Tag/ZIP 与独立还原。Phase 01–04 Tag/ZIP 保持不变，不进入 Phase 06。持久化默认关闭，本地配置及模板已补齐 session.persist/path。

## 实现与修改

- mybot/storage/session_store.py、__init__.py：v1 完整轮次 JSON，角色/字段/工具 ID 校验、同目录临时写入/fsync/replace、clear 原子保存空历史。
- agent/session.py：deepcopy 导出与恢复、当前 max_turns 整轮窗口。
- agent/loop.py：启动加载，磁盘保存成功后才提交内存；clear 磁盘成功后清内存；不恢复 Plan 或重放工具。
- config.py、配置模板、.gitignore：类型检查，项目根相对路径、workspace 外存储、忽略 .mybot_state。
- scripts/check_persistence.py、check_phase.py：16 项测试；旧阶段模拟测试明确 persist=false，避免写真实状态。
- scripts/phase_zip.py、test_phase_archives.py、AGENTS.md：拒绝状态目录/可识别 Session JSON 归档，测试隔离当前源码。
- docs/phases/phase-05.md、索引、README：完整学习教程与使用方法。

## 验证

Persistence 16 项测试通过：保存/重启、多工具配对、整轮淘汰、clear 一致性、超时/异常不写、上限收尾、replace/fsync 故障、损坏/版本/角色/ID 拒绝、关闭行为、Plan 不恢复、工作区权限边界、配置、深拷贝/权限。Session 12 项、Planning 12 项及原有工具日志回归通过，开发源码编译通过（排除 AppleDouble）。真实 LLM 手工验证未执行。

## 决策与局限

JSON 仅必要消息，不存系统/配置/Key/Plan 对象。文件损坏阻止启动并保留原文件。保存失败内存不变；工具副作用不回滚。clear 写空文档，不删除工作区文件。无多进程写、加密、目录 fsync、电源故障耐久保证、版本迁移、数据库、RAG 或长期记忆；仍按轮次非 token 裁剪。

## 环境与用户改动

macOS/zsh、Python 3.12+、uv；运行 uv run python mybot/main.py。session.persist 默认 false，path 默认 ./.mybot_state/session.json，max_turns 默认 6，修改重启生效。路径在 workspace 外；自定义目录需自行忽略。

app.py、workspace/instructions/USER.md 原有修改与未跟踪 workspace/summary.txt 保留，不提交。敏感配置和真实历史不输出、不提交。新目录/文件在 APFS 请求 0700/0600，ExFAT 通常不执行这些权限；复制尽量 COPYFILE_DISABLE=1，归档排除 ._*，临时独立验证使用 APFS。

## 下一步

完成 Phase 05 独立归档，之后由用户指定任务。不覆盖旧 Tag/ZIP，不重复实现 SessionStore，不进入 Phase 06。历史原理放 docs/phases，交接只保存当前状态。
