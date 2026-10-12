# AI Handoff

## 当前目标与状态

Phase 03 Session 已实现并通过离线测试，待本次提交、phase-03 Tag 与 ZIP 独立归档。Phase 01/02 已完成且 Tag/ZIP 保持不变。不进入 Phase 04。

## 实现与修改文件

- mybot/agent/session.py：deque 保存最近 6 个完整轮次，深拷贝读写，clear。
- mybot/agent/loop.py：独立 Session，结束时提交当前轮次，/clear；超时/异常丢弃当前轮，上限在完整工具结果后保存结束提示。
- mybot/agent/context.py、__init__.py：System→历史→当前 User，导出 Session。
- scripts/check_session.py、check_phase.py：10 项模拟 LLM 测试加入通用归档检查。
- docs/phases/phase-03.md、索引、README：完整教程与运行说明。
- 工具协议和路径权限不变，无新依赖、数据库或持久化；历史按整轮裁剪，不按 token 裁剪。

## 验证

- Session 10 项测试通过：首轮/次轮、多工具 id 配对、6 轮淘汰、CLI clear、ReAct 上限、API/asyncio 超时、工具错误、异常回退、深拷贝与隔离。
- Phase 01/02 通用工具及日志回归通过；开发源码编译通过（排除 AppleDouble）。
- 真实 LLM 手工记忆验证未执行，模拟测试仅证明请求包含历史。

## 环境与已知问题

macOS/zsh、Python 3.12+、uv；运行 uv run python mybot/main.py。debug 在 config/config.json 顶层，默认 false，修改后重启。

超时或异常不提交当前轮历史，但工具文件副作用不回滚。6 轮不保证符合模型 token 上限；不支持并发调用同一 Session，退出后记忆消失。

mybot/app.py 原有注释修改保留未提交。敏感配置不输出、不提交。ExFAT 可能生成 ._*；复制使用 COPYFILE_DISABLE=1，归档排除元数据，独立验证在 APFS 临时目录。

## 下一步与不要重复

完成本次 Phase 03 归档；后续目标由用户指定。不要覆盖已有 Phase Tag/ZIP，不重复实现 Session，不进入 Phase 04。历史原理放 docs/phases，本文件只保留当前状态。
