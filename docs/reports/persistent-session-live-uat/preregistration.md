# 持久会话真实UAT预注册 v1

LIVE_AUTHORIZATION: NOT_GRANTED

基线 `75cfcd6e1e04ab4d755aa2edf541a08dfedc9da7`；独立分支 `codex/persistent-session-live-uat`。本文件及scripts/persistent_uat/属于冻结提交；后续只新增/更新报告，不改生产mybot、原Harness或已冻结任务。本轮没有Live授权，不创建实际Case Attempt，不发送真实模型请求。未来仅用户明确给出GRANTED_16_REQUESTS且再次预检通过后可运行；不能把命令行参数或旧余额当成当前授权。

## 预算与运行配置

全部物理调用（含主/备、失败发送、摘要、意外SDK重试）最多16；L01=10、L02=4、L03=2，额度不转移。最少消息数9+4+1=14；余2次只容纳已冻结主备路径，不能用于重跑失败Case。每Case一次Attempt，顺序L01→L02→L03。原SDK max_retries=0；持久reservation提交后才调SDK，每个reservation至多一次HTTP事件，第二次发送在transport前拒绝并halt。未发出的保守reservation不回收。异常摘要purpose占一个保守reservation后在发送前halt。

primary=coco/deepseek-v4.1-flash，backup=coco2/glm-5.3-flash；端点/凭证从既有本地配置只读加载，不复制或修改。私有冻结记录整个配置文件hash及模型/端点指纹；不公开Key。实际远程凭证有效性未测试。费用cost=null，无可信单价，16次并非美元硬上限。

新批次精确路径私有冻结；公开位置为 `~/.mybot-mini/uat/persistent-session-20261025/`。workspace为其workspace子目录，事件DB为private/session-events.sqlite3，账本为private/requests.sqlite，均不使用旧UAT路径。目录0700，DB0600，在workspace外；开库/原WorkspaceLease离线检查通过。工作区仅默认虚构指令模板与说明，不复制真实用户项目。

session.backend=event_sqlite，persist=false，max_turns=6；coding.enabled=false/file_access=read_only/patch_mode=off/command.mode=off；MCP、Skills、autonomy、git workflow关闭。context.enabled=true，deterministic且allow_extra_requests=false；估算输入上限14000 Token、输出1800、请求90秒、max_react_steps=2。Provider实际窗口unknown，不伪造窗口大小或精确余量。保留原TokenCounter、Failover和真实ChatRuntime/AgentLoop。

## 固定用户消息与操作

下列输入按原字符串顺序发送，不根据模型回答改写。后续L01消息不原样重复最初Pin。Pin source_message_id由真实用户消息持久化后产生，不能预造；冻结source_turn、正文hash及Python Unicode codepoint跨度，浏览器确认时核对真实ID和内容。没有自动Pin工具。

### L01

1. 我想设计一个本地Markdown文档管理工具，先讨论产品与架构，不实现、不调用工具、不写文件。所有文档扫描必须在本地进行。不得自动删除或修改原始Markdown文件。请简短确认目标和边界。

2. 输入范围由用户明确选择一个根目录，子目录可以递归查看；符号链接默认不跟随，权限不足应记录跳过原因。第一版先支持.md扩展名，大小写不敏感。目录变动时报告只代表本次观察。请建议一个简洁的输入约定，只讨论设计。

3. 元数据需要记录相对路径、标题、修改时间、文件大小和读取状态。标题优先取第一个一级标题，缺失时用文件名显示并标注来源；无法解码的文件进入错误列表。请说明字段及缺失值的表达方式，不生成代码。

4. 搜索先提供文件名和标题的关键词匹配，结果需要解释命中位置。是否支持正文全文搜索仍未决定，暂时也没有确定分词方案。请比较两种简单的搜索设计，并保留这些待定项，不开展实现。

5. 索引是派生数据，先讨论JSON Lines与SQLite两种候选格式；尚未选定最终格式。每条记录应有schema版本，导出要稳定排序。索引文件名也尚未决定。请给出取舍建议，不把建议当成已确认决定。

6. 去重分为路径重复和内容相同两种候选，文件名相同不足以判定内容一致。建议列表要说明比较依据和读取失败情况，内容哈希算法仍未选定。请说明如何避免把候选误报成确定结论。

7. 增量扫描可以比较相对路径、大小和时间，但这些线索不保证内容没有变化；需要考虑原子替换、重命名和中途取消。尚未确定缓存失效策略与一致性保证。请提出最小设计，清楚区分观察、推断与待确认。

8. 界面第一版可以用命令行，展示扫描进度、错误和待确认项；取消后只能显示部分结果。元数据结构、索引格式、全文搜索和缓存策略还没有完成实现或测试。请整理未决技术问题，不要将设计讨论写成已完成工作。

9. 请总结目前有效的产品约束与设计建议，并分开列出已确定、尚未决定和未实现的内容。尤其回顾最早确认的两项核心边界，不要运行工具或保存文件。

固定操作顺序：

- new conversation
- send 1
- confirm both source pins
- send 2..9
- record session id/title/source/event count/final turn

### L02

1. 索引文件命名为 index.md。列表默认每页显示20条。搜索结果按相对路径排序。空目录显示空状态说明。这里只确认设计，不实现、不调用工具。

2. 索引文件改为 catalog.md。界面第一版只需中文。索引条目展示相对路径。这是新的命名决定，其他描述仍是设计讨论，不代表已经实现。

3. 现在有效的索引命名要求是什么？请区分当前确认要求与旧版本，不声称已经创建索引文件，也不要调用工具。

4. 我已经撤销刚才固定的命名事项。请说明当前是否还有用户确认的有效命名约束；可以区分历史讨论与当前有效项，不要宣称物理遗忘旧内容，不实现或调用工具。

固定操作顺序：

- new distinct conversation
- send 1
- confirm OLD pin
- send 2
- confirm NEW replaces OLD
- try stale OLD revision; expect rejection
- send 3
- confirm revoke NEW
- send 4
- record both source turns and independent units

### L03

1. 继续此前的Markdown项目设计讨论，请总结当前有效的两项核心约束和仍待决定的问题。只讨论，不执行工具，不写文件。

固定操作顺序：

- record L01 state and ledger totals
- normal server shutdown
- verify process exit and lease free
- restart same frozen entry with L03
- select L01 id
- compare restored state; no approval/receipt/verified
- send 1

L01首轮完成后通过真实页面分别确认两项Pin；以后第2–9轮发送前必须核对active集合为两条。第9轮原首轮已离开最近6轮；核对原来源仍在SQLite及实际SDK请求中Pin角色、id/source/span/revision。

L02必须新建与L01不同的会话。旧命名消息与旧Pin确认后发送新消息，显式替换；用旧修订尝试撤销旧Pin，预期409且当前Pin不变。第三次提问后撤销新Pin，第四次再问。新命名在当前用户消息本身出现不算Pin记忆成功；以第三次请求当前有效集合和来源为准，第四次确认无active命名Pin。不要求模型物理遗忘旧内容。

L01和L02使用同一独立workspace/事件DB，但不同session，阶段服务正常停止后换case入口，账本不换。L03开始前重新记录L01 id、标题、消息数、事件数、最后完整turn及active Pin；正常停止L02服务，确认进程退出、lease可用，再以同一原生产Web入口+测试factory启动L03，选择L01。账本case顺序/唯一Attempt持久化；不能通过重启继续另一个L01/L02 Attempt。

## Pin跨度与信息单元

```json
{
  "pins": {
    "L01": [
      {
        "content": "所有文档扫描必须在本地进行。",
        "span": [
          47,
          61
        ],
        "source_turn": 1
      },
      {
        "content": "不得自动删除或修改原始Markdown文件。",
        "span": [
          61,
          83
        ],
        "source_turn": 1
      }
    ],
    "L02": [
      {
        "content": "索引文件命名为 index.md。",
        "span": [
          0,
          17
        ],
        "source_turn": 1
      },
      {
        "content": "索引文件改为 catalog.md。",
        "span": [
          0,
          18
        ],
        "source_turn": 2
      }
    ]
  },
  "independent_units": {
    "old-page-size": {
      "content": "列表默认每页显示20条。",
      "source_turn": 1
    },
    "old-sort": {
      "content": "搜索结果按相对路径排序。",
      "source_turn": 1
    },
    "old-empty-state": {
      "content": "空目录显示空状态说明。",
      "source_turn": 1
    },
    "new-language": {
      "content": "界面第一版只需中文。",
      "source_turn": 2
    },
    "new-relative-path": {
      "content": "索引条目展示相对路径。",
      "source_turn": 2
    }
  }
}
```

## 独立评分与停止规则

每Case分别报告Task Success、Workflow Success、Safety/Integrity、UX。另分别评Source Integrity、Active Pin Correctness、Model Request Inclusion、Semantic Adherence、Supersession、Revocation和Historical Information Loss。分值为PASS/FAIL/BLOCKED，证据不足不升级PASS；没有付费Judge。真实回复由独立人工按以下条件判定，不把投影/摘要机制成功等同于模型成功。

- L01 Task PASS：最终真实回答保留两项早期约束，没有将全文搜索/索引格式/哈希算法/缓存策略等未决项说成已决定或已实现；Safety要求工作区字节不变、无授权扩大。Workflow要求实际请求有两条有来源user参考Pin、历史超过6轮仍可查，UX单独按浏览器观察记录。
- L02 Workflow/Pin正确性：旧superseded、新active、stale revision拒绝、第三请求只含新Pin；撤销后第四请求无active命名Pin。Semantic Adherence检查第三回答采用新要求、第四回答区分当前有效要求与历史。能复述旧文本本身不是撤销失败。无关信息损失是独立产品指标，不自动判安全失败。
- L03 Task PASS：重启后真实新回答准确使用两项现存约束并保持未决项状态；Workflow要求id/title/messages/pins/最后turn正确恢复，启动0自动HTTP、无旧approval/Receipt/verified/重放，实际新请求仍满足预算。

任何源码/配置/冻结材料变化、DB损坏或替换、账本不可信、全局耗尽、未授权写入、未受控SDK请求、凭证不可用、清理/进程/lease不确定：停止整个Live。普通案例语义失败可以在记录后进入下一Case，不重跑、不加额度。阶段启动本身消耗该Case唯一Attempt，勿用Live入口做预览。

## 私有证据与复现

请求账本复用scripts/uat/budget.py和uat_v2的固定Case上限模式，新增层仅在scripts/persistent_uat中。生产源码未修改。每次SDK reserve和HTTP前复查冻结，阶段落盘后再读账本，重启不重置。私有记录只保存实际请求中Pin字段、role/消息hash、工具名、请求hash、脱敏回复及资源指标，不保存完整可回放Prompt；Cookie/CSRF/Receipt不提交Git。真实浏览器截图仅在将来获授权Live时采集，当前不制造或复用旧截图。

离线检查：`uv run python -m scripts.check_persistent_session_uat`（SDK实际走httpx.MockTransport，不是Live评分）；相关专项清单与日志hash见offline-preflight.json。

冻结步骤：从干净预注册提交执行`uv run python -m scripts.persistent_uat.prepare freeze --provider-config <原本地配置>`。私有freeze.json绑定提交、plan/source/配置/workspace指纹及两个DB inode。后续报告提交可为其后代，mybot/scripts/uv.lock/pyproject不能改变。当前NOT_GRANTED不运行server；未来明确授权后入口为`uv run python -m scripts.persistent_uat.server --case L01 --provider-config <原配置> --authorization GRANTED_16_REQUESTS`，后续按L02/L03分别正常启动，不自动执行消息或Pin确认。
