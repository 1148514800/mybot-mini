# Phase 05：Session 持久化与恢复

archive-ready: true

## 1. 学习目标与核心概念

让同一份最近对话历史在 CLI 退出和重启后仍可使用，理解序列化、格式验证、原子替换以及内存/磁盘一致性。保持一个模型、现有 ReAct 和 Planning，不增加数据库、框架、RAG 或长期记忆检索。

Session 是进程内的完整轮次队列；Message History 是发送给模型的消息序列；Persistence 是将这些轮次保存到磁盘并重新加载。这里的持久化仍只保留最近 N 轮，并不是知识库、语义搜索或长期记忆。模型不会自动知道上次 API 请求的内容：重启后应用恢复消息，再把 System→历史→当前 User 重新发送，模型才能看到先前信息。

## 2. 完整架构与执行流程

```text
main → app → GatewayConfig / 工具 / ContextBuilder / AgentLoop
构造 AgentLoop：Session + 可选 SessionStore
  persist=false：不读取、不写入、不清除磁盘历史
  persist=true：SessionStore.load → 格式/版本/消息配对验证
               → Session.restore → 按当前 max_turns 保留最近 N 轮
每轮用户输入：原有 DIRECT/PLANNED 和 ReAct
  正常结束或配对完整的步数上限报告
    → 当前轮次 + 旧完整轮次 → 按 N 轮截取
    → SessionStore.save → 同目录临时 JSON → flush/fsync → os.replace
    → 成功后 Session.add_turn
  超时/异常：沿用原有回退，不保存当前轮
/clear：Plan reset → SessionStore.clear（原子保存空轮次）
                   → 磁盘成功后 Session.clear → 返回成功确认
```

每轮结束就写盘，退出无需额外保存。未完成的临时请求列表不进入磁盘，因此重启不会恢复半个工具调用组。

## 3. 核心源码与职责

| 文件 | 职责 |
| --- | --- |
| mybot/storage/session_store.py | JSON v1 文档、完整轮次校验、加载、原子保存、清空 |
| mybot/storage/__init__.py | 精简存储包 |
| mybot/agent/session.py | deque 窗口、deepcopy、export_turns/restore/max_turns |
| mybot/agent/loop.py | 启动恢复、完成保存、clear 一致性，保持 Planning 任务生命周期 |
| mybot/config.py | session.persist/path/max_turns 类型验证与项目根路径解析 |
| mybot/agent/context.py | 原有 System/历史/User 合并，未改变 |
| mybot/agent/planning.py | 原有任务内 Plan，未增加断点恢复 |
| scripts/check_persistence.py | 16 项 tempfile 和模拟 LLM 测试 |
| scripts/check_phase.py | Phase 01–05 通用验证入口 |
| scripts/phase_zip.py | 归档拒绝状态目录和识别出的 Session JSON |
| .gitignore、config/config.example.json | 本地状态忽略和默认关闭配置 |

## 4. JSON 序列化、格式和反序列化

使用 JSON，不使用可以执行任意对象恢复逻辑的 pickle。最外层明确保存 version 和 turns，而不是把扁平消息按 role 猜测切成轮次：

```json
{
  "version": 1,
  "turns": [
    [
      {"role": "user", "content": "我喜欢 Python"},
      {"role": "assistant", "content": "记住了"}
    ]
  ]
}
```

序列化由 json.dump 完成，UTF-8、ensure_ascii=false 保留中文；json.load 恢复普通字典、列表、字符串。版本必须是整数 1，布尔 true 不是版本号。未知字段、非列表轮次、不支持版本、无效 JSON 或 UTF-8 会拒绝恢复，不静默忽略、修复或覆盖。

存储只包含 user/assistant/tool 消息，不包含 System Prompt、配置、客户端 Key 或 Plan 对象。规划工具的原始请求和结果仍是合法历史消息；这不等于恢复计划执行状态。

## 5. 为什么工具消息必须成组保存

一个工具轮次可能有 user、assistant.tool_calls、多个 tool 结果、后续 assistant/tool 循环、最终 assistant 回复。validate_turns 校验每个轮次从一个 user 开始、最终 assistant 结束，且：

- assistant 发出的非空工具调用都有合法 function、字符串 arguments 和唯一 id；参数字符串可以包含非法 JSON，因为历史中的工具可能已返回相应解析错误。
- 每个 tool.tool_call_id 必须属于当前待回答集合，不能重复或凭空出现。
- 所有待回答 id 清空后才允许下一个 assistant。
- 不允许 System、夹在轮次中的第二个 user、中途非工具最终回复或额外字段。

校验整份磁盘记录后才裁剪旧轮次，坏的旧记录也不会被静默跳过。deque(maxlen=N) 以轮次为单位淘汰，避免留下孤立 Tool Result。

## 6. SessionStore 与 AgentLoop 的关键调用

Session.export_turns 返回完整轮次的深拷贝。restore 深拷贝并重建同一 maxlen 的 deque，磁盘历史超出当前 N 轮时自动保留最新 N 轮；启动不会立即改写文件，下一次完整结束才保存裁剪后的版本。

SessionStore.load 不存在文件时返回空列表；存在但无效时抛出明确 RuntimeError，错误描述不打印聊天正文，原文件保留。AgentLoop 构造时先加载并验证，再接入当前 Session；启动失败不会产生模型请求。

_finish_turn 沿用 Planning.close 的最终回复规则，生成完整 assistant 结束消息。它先准备旧轮次加当前轮次的窗口副本，调用 store.save，成功才向内存 Session 添加当前轮。保存失败会报告运行时错误，旧磁盘和旧内存保持不变，不显示“保存成功”。这不会回滚已经执行的文件工具副作用，也不是文件工具和历史存储之间的跨文件事务。

/clear 用 store.clear 原子写入 `{"version":1,"turns":[]}`，成功后清内存；磁盘清除失败时保留旧内存与磁盘并报错。空状态文件仍存在，但不含聊天记录。不删除 workspace 的任何文件。Plan 在当前输入开始时重置，不保留可继续执行的旧状态。

## 7. 原子写入、权限与路径安全

直接打开历史文件写入可能先截断旧记录，再因错误只写了一半。save 先验证完整轮次，然后创建同目录临时文件，写完 flush 和 fsync，再 os.replace。替换成功前旧文件不受影响；失败清理临时文件。临时文件与目标在同一目录，避免跨文件系统移动失去原子替换能力。

新建目录请求 0700，NamedTemporaryFile 默认文件 0600；替换后的新文件保留临时文件权限。不会随意 chmod 现有自定义共享父目录。macOS ExFAT 通常不执行 POSIX 所有者/权限限制，0700/0600 不能作为隐私保证；可将状态放到内置 APFS 的个人目录。JSON 明文存储，聊天内容本身可能包含敏感信息，没有加密。

文件 fsync 后替换保证正常文件系统上的一致更新；未实现目录 fsync、备份、校验和或电源故障后的完整耐久性承诺。存储设备和系统缓存也会影响突然断电后的行为。

默认文件为项目根目录的 .mybot_state/session.json，路径相对于项目根解析，与终端 cwd 无关。路径 resolve 后必须在 workspace 外；Store 每次读写也再次检查。原有文件工具会拒绝工作区外路径和指向外部的符号链接，模型不能通过工具读取或覆盖状态文件。恶意本地进程并发更改文件系统、预先制造硬链接不属于当前安全边界。

.mybot_state 已被 Git 忽略。自定义项目内存储目录也应自行加入 .gitignore；归档检查会拒绝默认目录以及可识别的 version/turns JSON，但不能替代敏感文件审查。

## 8. 配置与 macOS + uv 运行方法

```json
{
  "session": {
    "max_turns": 6,
    "persist": false,
    "path": "./.mybot_state/session.json"
  }
}
```

以上为 config.json 的 session 字段片段。max_turns 必须正整数，persist 必须 JSON 布尔，path 必须非空路径字符串，session 必须对象。默认关闭；明确设置 persist=true 并重启后开启。配置路径可以是工作区外的绝对路径，修改配置需重启。程序接口允许传入 Path，JSON 配置使用字符串。

```bash
bash scripts/restore_phase.sh 5
cd ../mybot-mini-learning/phase-05
uv sync --frozen
cp config/config.example.json config/config.json
# 填写本地 Key，并设置 session.persist=true
uv run python mybot/main.py
```

输入“我喜欢 Python”，退出后再次启动，再询问“我喜欢什么语言？”。模型此时会收到恢复历史；这是手工验证方法，真实 API 验证尚未执行。输入 /clear 后重启应为空历史。关闭 persist 时旧磁盘文件保留，但不读取、不写入、不清除。

## 9. 自动化测试与实际结果

```bash
uv run python -m scripts.check_persistence
uv run python -m scripts.check_phase
uv run python -m scripts.test_phase_archives
uv run python -m compileall -q mybot
```

tempfile 在 APFS 临时目录验证权限和原子替换；ExFAT 开发源码编译可以排除 `._*`：`uv run python -m compileall -q -x '/\._' mybot scripts`。旧 Phase 测试明确关闭持久化，避免测试误写真实会话；本阶段测试仅写临时文件。

16 项 Persistence unittest 均通过：正常保存与重建 Agent、多个工具 id 恢复、当前 max_turns 裁剪、clear 同步内存/磁盘/Plan、超时/异常不写、步数上限完整保存、replace/fsync 失败保留旧文件及清理临时文件、clear 失败一致性、损坏 JSON/版本/未知字段拒绝、消息配对与角色校验、关闭时忽略旧文件、规划历史恢复不重放、工作区访问与链接边界、配置类型和项目根路径、深拷贝与 0600/0700 权限。

Phase 01/02 工具日志回归、Session 12 项、Planning 12 项通过。归档测试覆盖默认状态目录与自定义命名 Session JSON 不可进入 ZIP；独立快照安装、编译和统一回归通过。真实模型手工测试未执行，不将模拟结果等同于模型恢复质量验证。

## 10. Phase 04 → Phase 05 与已知局限

Phase 04 只在进程内保留历史；Phase 05 可选跨重启恢复相同消息窗口。Planning 保持原有 DIRECT/PLANNED 选择，没有强制分类调用；旧 create_plan/update_plan 历史可以提供给模型，但 Plan 本身每轮重置，不会恢复断点或自动重新写文件。

不支持多进程写同一个文件、并发 Session、数据库、检索、RAG、长期知识记忆、事务回滚、自动恢复损坏文件、自动版本迁移或 Plan 恢复。按 N 轮而不是 token 限制，超长消息仍可能超过模型窗口。磁盘保存失败会拒绝内存提交，当前模型回答未加入历史；已执行工作区操作仍需人工确认。

Phase 01–04 Tag/ZIP 不变；保留 app.py、USER.md 和 workspace/summary.txt 的用户改动，不纳入本阶段归档。发生加载失败时先停止程序、备份并检查原文件；不要自动删文件或覆盖来“修复”。本阶段不进入 Phase 06。
