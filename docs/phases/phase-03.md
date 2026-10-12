# Phase 03：Session 多轮对话

archive-ready: true

## 1. 学习目标

理解 LLM 请求本身不记忆上一轮，如何由应用保存消息并重新发送历史。在同一个 CLI 进程中记住用户信息、完整保存工具调用链，并按用户轮次限制历史长度。能解释异常回退与工具副作用的区别。

## 2. Agent 核心概念

Session 是应用层会话状态，不是模型内部记忆。User 发起一轮，Assistant 可以连续请求工具，Tool 提供执行结果，Assistant 最后回答。一个用户轮次包含从 user 到最终 assistant 的所有消息，可能超过两条。

System 描述当前规则，历史对话提供先前事实，当前 User 提出新问题。每个 tool_call_id 必须与前面的 assistant.tool_calls 中对应 id 配对，不能仅按消息条数截断。进程内记忆在退出后消失，不包含数据库、长期记忆或多 Agent。

## 3. 完整架构与执行流程

```text
main.py → app.run_gateway → 配置 / 客户端 / 工具 / ContextBuilder / AgentLoop
AgentLoop 构造时创建独立 Session（默认 6 轮）
用户输入 → /clear：清空 Session，返回确认，不请求 LLM
         → Session.history：读取历史副本
         → ContextBuilder：System + 历史 + 当前 User
         → LLM → Assistant 工具请求 → 工具执行 → Tool 结果 → 再请求 LLM
         → 最终回答：保存当前完整轮次 → 超过 6 轮则移除最旧整轮
         → 超时/未捕获异常：不保存当前轮，旧 Session 不变
         → 步数上限：工具全部执行并配对 → 添加结束提示 → 保存完整轮
```

继续保留 read_file、write_file、list_files、有限 ReAct 循环、debug 日志、超时和工作区路径边界。

## 4. 核心代码文件及职责

| 文件 | 职责 |
| --- | --- |
| mybot/main.py | CLI asyncio 入口 |
| mybot/app.py | 配置、客户端、工具与 Agent 组装和资源关闭 |
| mybot/config.py | JSON 配置与 OpenAI 兼容客户端 |
| mybot/workspace.py | 工作区初始化 |
| mybot/agent/session.py | 完整轮次队列、深拷贝历史、清空 |
| mybot/agent/context.py | 当前系统指令与历史消息合并 |
| mybot/agent/loop.py | Session 接入、工具循环、结束提交、/clear |
| mybot/agent/__init__.py | 导出 Session、AgentLoop、ContextBuilder |
| mybot/tools/base.py、registry.py | Schema、ToolResult、统一工具执行边界 |
| mybot/tools/file.py、list_files.py | 现有三个工作区工具，协议及权限不变 |
| scripts/check_session.py | 模拟 LLM 的 Session 自动化测试 |
| scripts/check_phase.py | 通用回归与阶段专用测试入口 |

## 5. Session 原理、消息结构及关键函数

`Session(max_turns=6)` 用 deque(maxlen=max_turns) 存放“消息列表的列表”。`add_turn` 保存一整个用户轮次，deque 自动淘汰最旧轮次。`history` 展平保留的轮次并深拷贝；系统消息不保存到 Session。深拷贝避免构建当前请求或外部读取时修改已保存历史。`clear` 清空队列。max_turns 必须为正数，可在构造 Session 时调整，不新增配置文件字段。

普通轮次：

```json
[
  {"role": "user", "content": "我最喜欢的语言是 Python"},
  {"role": "assistant", "content": "记住了"}
]
```

工具轮次：

```json
[
  {"role": "user", "content": "列出文件"},
  {"role": "assistant", "content": null,
   "tool_calls": [{"id": "call-1", "type": "function",
      "function": {"name": "list_files", "arguments": "{\"path\":\".\"}"}}]},
  {"role": "tool", "tool_call_id": "call-1", "content": "[FILE] note.txt"},
  {"role": "assistant", "content": "目录中有 note.txt"}
]
```

`ContextBuilder.build_messages(user_message, history=None)` 每轮重新读取工作区说明文件，输出一个 System、历史消息和当前 User。第二参数可省略，旧单轮调用仍可使用。

`AgentLoop` 默认拥有一个 Session，也可传入独立 Session。`handle_message` 先处理 /clear，再取得历史副本构建请求；turn_start 指向本轮 user，避免把系统或旧历史再次存入 Session。每次后续 LLM 请求继续使用同一临时 messages，其中工具请求、参数字符串、结果与 id 沿用原协议。

`_finish_turn` 在临时 messages 末尾补上 assistant 最终文本，然后只提交 messages[turn_start:]，防止历史重复或无限累积。空文本回复沿用“模型没有返回文本”提示并结束当前轮。最终文本与 CLI 回复一致。

## 6. 新增功能与错误处理

- 同一 CLI 进程的后续输入会看到最多最近 6 个已完成用户轮次；当前输入另占一轮，构建请求时历史可以有 6 轮。
- /clear 清空历史，返回确认，不请求模型、不保存为用户轮次；退出/重启也会丢失记忆。
- 工具报错仍产生匹配的 Tool 消息，模型可总结错误，完整轮次正常保存。
- 模型超时返回原有超时提示，但不提交当前轮；未捕获运行时异常和中断同样不提交临时历史。之前成功轮次保持不变。
- 达到 ReAct 上限时，本步所有工具已经得到结果，随后添加 assistant 上限提示并保存，确保下一轮无悬空调用。
- 不改变 read_file、write_file、list_files 或路径权限，不增加框架或依赖。

## 7. macOS + uv 安装、运行和测试

```bash
bash scripts/restore_phase.sh 3
cd ../mybot-mini-learning/phase-03
uv sync --frozen
cp config/config.example.json config/config.json
# 填写本地 API 凭证
uv run python mybot/main.py
```

需要 Python 3.12+、uv，终端使用 zsh。debug 在配置文件中设置 true/false，修改后重启。历史默认保留 6 轮。

```bash
uv run python -m scripts.check_session
uv run python -m scripts.check_phase
uv run python -m compileall -q mybot
```

ExFAT 开发目录若出现 AppleDouble，可使用 `uv run python -m compileall -q -x '/\._' mybot scripts`；归档验证在 APFS 临时目录执行完整编译。

## 8. 实际测试案例和结果

10 项标准库 unittest 使用模拟 LLM，无真实 Key、无 API 请求，均通过：

| 案例 | 验证内容 |
| --- | --- |
| 首轮与第二轮 | 首轮 system/user；第二轮 system/上一轮 user/assistant/当前 user，包含 Python 信息 |
| 多工具请求 | write_file/read_file 按顺序执行，两个 id 各有 Tool 结果，下一轮完整保留 |
| 历史淘汰 | 连续 7 个工具轮次后只保留第 2–7 轮，旧请求及结果一起移除 |
| CLI /clear | 不新增模型请求，清空历史，下一轮只有 system/user |
| 步数上限 | 保留 user/assistant.tool_calls/tool/assistant 提示，下轮消息有效 |
| API 超时 | 工具执行后发生 APITimeoutError，当前轮不入历史，旧轮保留；已写文件不回滚 |
| asyncio 超时 | 实际 wait_for 超时，历史为空 |
| 工具错误 | 缺失文件错误作为 Tool 返回，id 配对正确 |
| 未捕获异常 | 模型请求异常不污染旧历史 |
| 副本与隔离 | 输入和历史副本修改不影响 Session；新 Session 无旧数据，非法轮数拒绝 |

通用 Phase 01/02 文件工具与日志回归通过；快照独立执行 uv sync --frozen、compileall 和上述统一检查。模型记忆测试检查实际发出的请求，不以固定模拟答复证明真实模型理解。

手工验证方法：第一轮输入“我最喜欢的语言是 Python。”，第二轮输入“我刚才说我最喜欢什么语言？”，预期回答 Python，再输入 /clear 后检查记忆消失。真实 LLM API 手工验证尚未执行，不宣称线上验证成功。

## 9. 常见问题与注意事项

- 超时轮不入历史，但已执行工具的文件变更不会回滚；需要时重新读取文件确认实际状态。
- 历史按轮次限制，不按 token 限制；很大的工具结果仍可能超过模型上下文窗口。没有摘要或 token 裁剪。
- Session 不支持持久化、并行处理同一会话或跨进程共享；CLI 顺序处理输入。
- 本地失败提示不是模型生成的回答：超时不入历史；步数上限提示作为结束 assistant 入历史。
- Session.add_turn 是内部提交接口，调用者负责传入完整轮次；正常 AgentLoop 只在完整结束时调用。
- /clear 清空内存，不删除工作区文件、配置、日志或 ZIP。
- 每轮系统规则重新读取，因此修改 instructions 会影响之后请求。配置仍需重启加载。
- 恶意并发文件系统修改不在当前权限边界保证范围内，沿用 Phase 02 限制。

## 10. Phase 02 → Phase 03

Phase 02 为每条用户输入独立构建消息，只有同一 ReAct 循环内的工具上下文。Phase 03 在原架构上增加独立 Session 和结束提交边界，实现跨输入的完整轮次记忆、6 轮窗口和 /clear。工具协议、权限、模型配置和调试日志保留。Phase 01/02 Tag、ZIP 和学习文档保持不变；原有 app.py 注释修改未混入本阶段。
