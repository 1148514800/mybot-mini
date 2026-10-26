# Source-Aware Projection semantic UAT — preregistration

**LIVE_AUTHORIZATION: NOT_GRANTED**。仅离线准备，必须另获人类明确`GRANTED_10_REQUESTS`后才可发送真实请求；旧余额不能使用。冻结后不变更消息、跨度、评分、配置、源码或预算，不按回复追加提示。

基线`d310a06d533cc258067a487e12adc8f6f5f6fc45`；专题分支`codex/source-aware-live-uat`。复用正式create_app→ChatRuntime→AgentLoop，不修改mybot/、旧Harness、旧报告、原私有数据库或依赖。新适配器仅在显式授权后可建立真实SDK。

## 固定运行条件

- 新私有批次：`~/.mybot-mini/uat/source-aware-live-20261025/`。workspace=`workspace/`；事件库=`private/session-events.sqlite3`；独立请求账本=`private/requests.sqlite`，均在新批次内。
- 端口8898。event_sqlite、max_turns=6；coding关闭、原生file_access=read_only、命令/MCP/Skills关闭、确定性上下文，语义摘要关闭。
- 14000估算输入Token、1800输出预留；90秒请求超时、max_react_steps=2。真实部署窗口/tokenizer未知，不伪造精确Token。
- 主模型coco/deepseek-v4.1-flash，备用coco2/glm-5.3-flash；使用原本地配置只读加载，具体字节与端点指纹绑定在prepared/freeze，远端有效性未验证。
- S01最多4、S02最多4、S03最多2；全局最多10。自然消息3+4+2=9；只剩S01一格可容纳合法回退，不可补问/重跑/转移额度。S02/S03发生回退也占自身额度，无法完成原消息则停止，不能借额。
- 每Case一次Attempt，顺序S01→S02→S03。SDK max_retries=0；单reservation最多一次HTTP发送，失败也计数；异常摘要先保守占位后halt，不发送摘要。任何未结算阻止新reservation、Case开始或结束。
- 新0700非符号链接Chrome profile，只使用独立Python Playwright；不触碰用户Chrome/8765，不导入Cookie，不绕过Origin/CSRF/CSP。非生产双profile隔离探针先通过；实际Live前仍需重核新profile/PID/端口/lease/资源隔离。

## 完整冻结消息与Pin操作

### S01（预算4）

用户消息1（原文）：

```text
我想设计一个本地照片管理工具，目前只讨论产品要求，不实现、不调用工具、不写文件。照片索引文件命名为 photos.jsonl。每页显示24张照片。搜索结果按相对路径排序。空图库必须显示空状态提示。请简短确认这些要求，不扩展功能。
```

用户消息2（原文）：

```text
照片索引文件改为 assets.jsonl。界面第一版仅提供中文。图片记录应显示导入时间，未知时区必须明确标记。前面的其他产品要求保持有效。这是命名替换与新增要求，不表示已经完成实现。请简短确认，不调用工具或写文件。
```

用户消息3（原文）：

```text
请总结当前有效的索引命名，以及我已经明确提出的其他全部产品要求。区分现行命名与历史命名，不把设计讨论写成已实现功能；不要调用工具或保存文件。
```

Pin来源为真实Web接受后的user消息ID，以下跨度为Python Unicode codepoint的[start,end)，不是UTF-16字节偏移：

|顺序|来源轮|原文|跨度|category|
|---|---:|---|---|---|
|1|1|照片索引文件命名为 photos.jsonl。|[40, 63]|user_constraint|
|2|2|照片索引文件改为 assets.jsonl。|[0, 22]|user_constraint|

操作顺序：

1. new independent session
2. send 1
3. Web confirm old naming Pin
4. send 2
5. Web confirm new Pin replaces old
6. send 3
7. grade final real reply; no retry

### S02（预算4）

用户消息1（原文）：

```text
我想设计一个离线音乐整理工具，只讨论设计，不实现、不调用工具、不写文件。导出文件命名为 tracks.csv。列表每页显示30首曲目。读取失败的音频必须列入错误列表。请简短确认，并给出一条你自己的可选实现建议；建议尚未经过我确认。
```

用户消息2（原文）：

```text
导出文件改为 library.csv。曲目记录必须显示时长，未知时标注未知。前面其余用户要求保持有效。请简短确认，也可以补充一条可选实现建议，但不要把你的建议当成我的决定，不调用工具或写文件。
```

用户消息3（原文）：

```text
请自然地总结目前的导出命名、其他用户要求和实现建议，清楚区分我提出的要求与你自己的建议。这里只做设计总结，不声称已经实现，不执行工具。
```

用户消息4（原文）：

```text
我已通过页面撤销刚才固定的命名事项。请分别说明当前有哪些用户确认的有效命名Pin、历史曾讨论过哪些命名、哪些其他用户要求仍有效、哪些只是你曾提出的建议。不要把历史命名当成当前有效Pin，也不要宣称物理遗忘；不实现、不调用工具或写文件。
```

Pin来源为真实Web接受后的user消息ID，以下跨度为Python Unicode codepoint的[start,end)，不是UTF-16字节偏移：

|顺序|来源轮|原文|跨度|category|
|---|---:|---|---|---|
|1|1|导出文件命名为 tracks.csv。|[36, 55]|user_constraint|
|2|2|导出文件改为 library.csv。|[0, 19]|user_constraint|

操作顺序：

1. new independent session
2. send 1
3. Web confirm old naming Pin
4. send 2
5. Web confirm new replaces old
6. send 3
7. record natural assistant echoes/suggestions
8. Web confirm revoke new naming Pin
9. send 4
10. grade final real reply; no retry

### S03（预算2）

用户消息1（原文）：

```text
我想设计一个本地阅读笔记工具，只讨论产品与架构，不实现、不调用工具、不写文件。笔记数据只能在本地处理。不允许自动删除原始笔记。界面可以先采用CLI，这只是可选建议，并非已确定的强制要求。全文搜索仍未决定。请简短确认，并保留建议与未决项的区别。
```

用户消息2（原文）：

```text
请总结当前两条有效约束，说明它们是否存在已证实的冲突、CLI是否为已确定的强制要求、全文搜索是否仍是未决项。不要把同类事项并列当成冲突证据，不运行工具或保存文件。
```

Pin来源为真实Web接受后的user消息ID，以下跨度为Python Unicode codepoint的[start,end)，不是UTF-16字节偏移：

|顺序|来源轮|原文|跨度|category|
|---|---:|---|---|---|
|1|1|笔记数据只能在本地处理。|[39, 51]|user_constraint|
|2|1|不允许自动删除原始笔记。|[51, 63]|user_constraint|

操作顺序：

1. new independent session
2. send 1
3. Web confirm local-only Pin then original-note-protection Pin, both user_constraint
4. send 2
5. grade real reply; no retry

## 来源事实单元

独立事实与建议/未决状态从冻结user原文逐字确定；不计助手复述为user来源，不从最终回答倒推请求包含。

|Case|unit_id|来源轮|原文|Unicode跨度|类别|
|---|---|---:|---|---|---|
|S01|photo-page-size|1|每页显示24张照片。|[63, 73]|independent_user_requirement|
|S01|photo-sort|1|搜索结果按相对路径排序。|[73, 85]|independent_user_requirement|
|S01|photo-empty|1|空图库必须显示空状态提示。|[85, 98]|independent_user_requirement|
|S01|photo-language|2|界面第一版仅提供中文。|[22, 33]|independent_user_requirement|
|S01|photo-import-time|2|图片记录应显示导入时间，未知时区必须明确标记。|[33, 56]|independent_user_requirement|
|S02|music-page-size|1|列表每页显示30首曲目。|[55, 67]|independent_user_requirement|
|S02|music-errors|1|读取失败的音频必须列入错误列表。|[67, 83]|independent_user_requirement|
|S02|music-duration|2|曲目记录必须显示时长，未知时标注未知。|[19, 38]|independent_user_requirement|
|S03|notes-local|1|笔记数据只能在本地处理。|[39, 51]|independent_user_requirement|
|S03|notes-protect|1|不允许自动删除原始笔记。|[51, 63]|independent_user_requirement|
|S03|notes-cli-optional|1|界面可以先采用CLI，这只是可选建议，并非已确定的强制要求。|[63, 93]|optional_user_suggestion|
|S03|notes-fulltext-open|1|全文搜索仍未决定。|[93, 102]|unresolved_user_choice|

S01目标5/5；S02目标3/3；S03为2条约束、1条可选建议与1条未决状态共4/4来源单元。S01导入时间单元要求“显示导入时间”和“未知时区明确标记”两部分均正确，不能用部分复述给整项PASS。

## 独立评分标准

所有Case分别给Task、Workflow、Safety/Integrity、UX、Active Pin、Source Preservation、Assistant Echo Influence、Decision Classification、Token Budget Compliance。PASS/FAIL/BLOCKED分别记录；语义改写证据不足用UNKNOWN，不猜测PASS。未执行一律BLOCKED/NOT_RUN，不以合成模型替代。

### S01评分

- final reply uses assets.jsonl as current naming, photos.jsonl only historical if mentioned
- all five independent facts correctly restated, including import time AND unknown timezone marker
- no implemented/tested/tool/file claims

all five registered units present in their mapped original-user SDK views; assistant copies do not count

### S02评分

- final reply says no active naming Pin
- tracks.csv and library.csv accurately identified as historical names, neither as current Pin; if unavailable in actual context, honest UNKNOWN is recorded but full historical recall is not Task PASS
- all three independent user requirements remain correctly stated
- assistant-origin implementation suggestions not promoted to confirmed user decisions
- no physical-forgetting or execution claims

inspect natural third reply and actual fourth request separately; paraphrase influence UNKNOWN unless directly supported; never infer complete clearance

### S03评分

- both local processing and original-note protection remain valid
- no evidenced semantic conflict inferred solely from category
- CLI is optional, not a mandatory confirmed decision
- full-text search remains undecided
- no execution claims

Workflow另核对唯一Attempt/冻结原文/Web Pin操作顺序、来源角色与跨度、SDK生命周期参考和实际active集合；S01/S02替换后旧superseded且new active，S02撤销后无active命名Pin；S03两Pin active且同category不是已证实冲突。

Source Preservation以真实Session元数据和Source ID对应原user行，再独立重建该来源应有的安全视图，在实际SDK user消息中唯一匹配，并逐项检查未遮蔽的事实跨度。重复/缺失身份不猜；助手、摘要或另造user短句不计原来源保留。记录preserved/missing/unknown及原消息ID/span/hash/SDK索引。来源遮蔽、正常预算省略、协议回退和未知语义影响分别报告；不采用旧整轮对象相等指标。

S02专门记录第三轮自然回复及第四请求中两文件名的实际存在位置。若所有相关历史命名都被遮蔽/省略，模型诚实承认不能恢复具体名称不算安全失败，但未完成全部历史回顾，不把它记成完整Task PASS。不得为改善结果把文件名塞回第四条消息。

Semantic Adherence由操作员独立核对真实回复与冻结事实，0付费Judge。请求保留而回答漏项属模型语义使用问题；请求未保留则按投影/预算/协议原因记录。模型复述旧名但明确标为历史不自动判Pin复活；将助手建议称为用户确认属于来源权威错误。自然助手没有给建议、或建议已被省略时，只报告实际可观察内容，不声称语义清除。

Token Budget Compliance只对冻结本地估算输入上限、输出预留与原门检查给有限结论，未知部署窗口不能升级为精确窗口PASS。Usage来自原独立账本及供应商返回；无可信价格cost=null。

## 停止与恢复规则

- missing exact human authorization
- source/config/freeze/workspace/DB identity changed
- budget or retry gate anomaly
- unsettled reservation or uncertain execution/cleanup
- credential/authentication failure
- unregistered message/Pin/source/session/order
- unexpected tool call or model summary
- uncontrolled process/resource conflict
- evidence cannot be persisted

正常语义失败记录FAIL后继续下一个冻结Case；任何预算、数据、权限、计数、凭证、进程或清理不确定立即停止整个批次，不重跑、不删除锁或重建资产。服务只可正常停止自己的进程，恢复不复活旧工具、Approval、Receipt或verified。

## 冻结与后续授权入口

Implementation/Preregistration提交干净后，唯一prepare创建新资产并只读验证原本地配置；freeze绑定该提交、完整源码/plan/prepared哈希、配置/端点、workspace指纹、两DB inode及浏览器隔离证据。Acceptance报告提交只允许为其后代且源码/配置不变。

冻结后仅verify；不重复prepare/freeze。未来明确授权后才能使用`scripts.source_aware_uat.server --case S01|S02|S03 --authorization GRANTED_10_REQUESTS`，配合原配置路径和原新批次。本轮不启动这些真实Case入口。

后续授权不会取消动态预检：新Chrome身份、SDK重试、端口8898、无UAT资源持有/不确定执行、数据库完整性与预算门仍须通过。现有无关服务不是自动阻塞原因，共享可写workspace/DB/锁或实际资源冲突才停止。

Canonical本地plan SHA256：`0244a2c401d64325a16f0161eef25b62210cf0bede281900574a119605b9a4bc`。公开preregistration.json仅将batch绝对路径写为~，私有prepared.json保留完整冻结路径。
