# MyBot 浏览器工具

本目录提供 MyBot 的浏览器自动化能力。工具通过
[`playwright-cli`](https://github.com/microsoft/playwright-cli) 支持两种 Chrome：
连接用户已经打开的本地 Chrome，或启动 MyBot 管理的独立持久化 Chrome。

## 核心约束

- `local_browser` 通过 `browser_attach` 连接用户当前 Chrome，直接复用其登录状态。
- `managed_browser` 通过 `browser_open` 启动独立的可见 Chrome，登录信息保存在
  `workspace/browser_profiles/managed_browser`。
- `browser_open` 固定使用 Chrome、`--headed` 和受控的 `--profile` 路径；模型不能
  指定临时 profile、其他浏览器类型或任意文件路径。
- `exec` 工具禁止直接运行 `playwright-cli`，浏览器只能通过结构化的
  `browser_*` 工具操作。
- 未明确指定浏览器模式时默认使用 `browser_open`。只有用户明确提到本地浏览器、
  当前 Chrome、已打开的浏览器等含义时才使用 `browser_attach`。
- 两种模式失败时不会自动切换，防止操作错误的登录环境。

如果 `browser_attach` 失败，应先确认本地 Chrome 已打开并且下面的命令可以在
用户终端中正常执行：

```powershell
playwright-cli attach --cdp=chrome -s=local_browser
```

`managed_browser` 首次打开时可能需要手动登录。关闭 session 后 profile 不会删除，
下次调用 `browser_open` 会继续使用已有 Cookie、Local Storage 和站点登录状态。

## 目录结构

```text
browser/
  __init__.py       # 对外导出浏览器工具
  base.py           # CLI 进程、结构化结果、超时和输出截断
  session.py        # 显式管理活动 session，由全部浏览器工具共享
  connection.py     # 连接本地 Chrome
  navigation.py     # 持久化浏览器、页面跳转、标签页和 session 关闭
  interaction.py    # 快照、结构化 DOM 查询、点击、输入、链接提取和 JS
```

工具由 `mybot/tools/registry.py` 注册，并通过 OpenAI function calling schema
提供给模型。

## 可用工具

| 工具 | 作用 | 主要参数 |
|---|---|---|
| `browser_attach` | 连接本地 Chrome | 无 |
| `browser_open` | 启动并复用 MyBot 的持久化 Chrome | 可选 `url` |
| `browser_goto` | 在当前标签页跳转 | `url` |
| `browser_tab` | 列出、新建、选择或关闭标签页 | `action`、`index`、`url` |
| `browser_snapshot` | 获取带元素 ref 的可访问性快照 | `target`、`depth` |
| `browser_inspect` | 通过固定实现查询 DOM，不接受调用者 JavaScript | `selector`、`text`、`role`、`placeholder`、`limit` |
| `browser_verify` | 验证结构化 DOM/URL 后置条件，不接受调用者 JavaScript | `selector`、`text`、`role`、`placeholder`、`url_contains` |
| `browser_links` | 按视觉顺序列出并去重可见链接 | `target`、`url_contains`、`limit` |
| `browser_click` | 单击或双击元素 | `target`、`double` |
| `browser_type` | 输入或填充文本 | `text`、`target`、`submit` |
| `browser_press` | 按下键盘按键 | `key` |
| `browser_eval` | 在页面或指定元素上执行 JavaScript | `script`、`target` |
| `browser_close` | 结束当前 Playwright CLI session | 无 |

`browser_attach` 和 `browser_open` 会分别激活 `local_browser` 与
`managed_browser`。Agent 会根据当前用户消息选择模式，并把本轮所有后续浏览器
工具强制绑定到对应 session，避免上一轮使用过的浏览器影响本轮操作。

### `browser_tab` 动作

| `action` | 行为 | 附加参数 |
|---|---|---|
| `list` | 查看全部标签页和当前标签页 | 无 |
| `new` | 在当前 session 的 Chrome 中新建标签页 | 可选 `url` |
| `select` | 切换到指定标签页 | 必须提供从 0 开始的 `index` |
| `close` | 关闭指定标签页 | 必须提供从 0 开始的 `index` |

## 推荐工作流

默认模式启动 MyBot 管理的持久化 Chrome：

```json
{
  "name": "browser_open",
  "arguments": {"url": "https://www.bilibili.com"}
}
```

首次使用时在打开的 Chrome 中完成登录。后续操作复用 `managed_browser`，关闭后
再次调用 `browser_open` 仍会加载同一 profile。然后在该 session 中继续操作：

```json
{"name": "browser_goto", "arguments": {"url": "https://www.bilibili.com"}}
{"name": "browser_snapshot", "arguments": {"depth": 8}}
{"name": "browser_click", "arguments": {"target": "e42"}}
```

用户明确要求使用本地、当前或已打开的 Chrome 时，连接其本地浏览器：

```json
{"name": "browser_attach", "arguments": {}}
```

连接后在同一个 `local_browser` session 中导航和操作。若连接失败，不会自动改用
托管浏览器，以免在错误的登录环境中继续任务。

### 自动新开标签页的网站

某些搜索框提交后会自动打开新标签页。此时不要再把旧标签页导航到相同 URL，
否则会产生两个相同页面。正确流程是：

```json
{"name": "browser_tab", "arguments": {"action": "list"}}
{"name": "browser_tab", "arguments": {"action": "select", "index": 6}}
```

只有确认重复标签页是本次任务创建的，才使用 `action: "close"` 关闭。操作
`local_browser` 时尤其不要关闭用户原有页面。

### 选择第 N 个搜索结果

不要根据快照 ref 数字推测顺序，也不要同时计算同一卡片的缩略图链接和标题
链接。使用 `browser_links` 按页面坐标排序并按目标 URL 去重：

```json
{
  "name": "browser_links",
  "arguments": {
    "target": ".video-list",
    "url_contains": "/video/",
    "limit": 20
  }
}
```

结果中的 `position` 从 1 开始。取得第 N 项的 URL 后，直接调用
`browser_goto`，不要先点击同一结果再跳转一次。

### 结构化 DOM 查询

查找普通文本、输入框、按钮和属性时使用 `browser_inspect`，不要直接构造
`browser_eval` JavaScript：

```json
{
  "name": "browser_inspect",
  "arguments": {
    "role": "textbox",
    "placeholder": "发送消息",
    "limit": 10
  }
}
```

Tool 内部运行固定的只读查询并返回匹配元素的 role、文本、placeholder、href 和
可复用 target。调用者只能提供结构化过滤值，不能提供脚本。

Windows 下 Runtime 不通过 npm 生成的 `playwright-cli.cmd` shim 传递固定 JS；该 shim
会用 `%*` 二次解析括号、引号和 shell 元字符。Runtime 会解析同一安装目录中的 Node
入口并直接执行，从而保证 inspect/links 内部脚本作为一个原始 argv 传入。

### 完成验证

点击、填写、Enter/Space、提交、发送或发布动作成功后，使用 `browser_verify` 验证一次
具体后置条件。普通快照、输入成功或点击成功都不能单独证明任务完成；只有
`postcondition_met=true` 才能判定该动作达成目标。

失败结果通过 metadata 提供 `error_type` / `recoverable`。stale/not-found target 应重新
读取快照后定位；ambiguous target 应先用 inspect 缩小范围，必要时询问用户；
tool syntax error 不允许原样重复。是否重试由模型依据当前页面状态决定，Runtime 不
自动重试，也不施加任务级预算。

## 快照和输出限制

- `browser_snapshot.depth` 默认是 `8`，范围为 `1..20`。
- 快照使用 `--filename=` 强制在工具结果中返回 YAML，而不是只返回本地文件链接。
- 普通工具输出最多保留 `12000` 个字符。
- 快照输出最多保留 `30000` 个字符。
- 超出限制时结果末尾会包含明确的 `output truncated` 提示。
- 单条 CLI 命令超时时间为 `60` 秒。

大型页面应优先通过 `target` 获取局部快照，或降低 `depth`，避免无关导航、
页脚和推荐内容占用模型上下文。

## 操作原则

1. 导航后获取新快照，不复用已经失效的 ref。
2. 优先使用快照 ref；Snapshot 的 `[ref=e102]` 在 target 中应写 `e102`，不能写 `ref=e102`。
3. 普通 DOM 查询优先使用 `browser_inspect`，选择第 N 个结果优先使用 `browser_links`。
4. 已经获得目标 URL 时直接 `browser_goto`。
5. 最终状态最多验证一次，确认完成后停止调用工具。
6. `browser_eval` 仅作为 snapshot / inspect / links 无法完成读取时的需确认后备方案。
7. 任何标记为 `[browser error ...]` 的结果都视为失败，不应继续假设操作成功。

CLI 退出码为 0 但输出含独立 `### Error` block 时，Runtime 仍返回失败；网页
Console Error 不属于该 block，不会被误判为 Tool Failure。

## 常见问题

### `Browser 'local_browser' is not open`

当前 MyBot 进程还没有连接本地 Chrome，或之前的 session 已结束。重新调用
`browser_attach`。如果仍然失败，确认 Chrome 已打开并检查用户终端中的 attach
命令。

### `Browser 'managed_browser' is not open`

调用 `browser_open` 恢复持久化浏览器。如果 profile 已存在，它会继续使用原来的
登录状态。不要删除 `workspace/browser_profiles/managed_browser`，除非明确希望
清空该浏览器的全部登录数据。

### 新浏览器没有登录状态

第一次启动 `managed_browser` 是正常的空白 profile，需要手动登录一次。确认每次
都通过 `browser_open` 启动，并检查命令使用的 profile 是否为 README 中的固定
目录。登录后应正常关闭 session，不要删除 profile 目录。

### 操作后出现两个相同页面

通常是表单提交自动打开了新标签页，随后又对旧标签页执行了 `browser_goto`。
使用 `browser_tab` 的 `list` 和 `select` 切换到新标签页，不要重复导航。

### 第 N 个结果不准确

可访问性树顺序可能与页面视觉顺序不同，而且一张卡片可能有多个相同 URL 的
链接。使用 `browser_links`，设置结果容器 `target` 和目标 URL 的
`url_contains`。

### 快照内容不完整

检查结果末尾是否包含 `output truncated`。可以降低 `depth`，或把 `target`
设置为搜索结果列表、表格、正文等局部容器。

### 修改代码后行为没有变化

MyBot 在启动时加载工具和系统提示。修改本目录代码后，需要重启
`mybot/main.py`。

## 测试

运行全部单元测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

大多数单元测试会 mock CLI 调用；`test_browser_inspect_selector_text_role_and_placeholder`
会启动一个隔离的 headless Chrome、加载 `about:blank` 并在结束时自动关闭，用于验证
Windows CLI 参数传递和真实 DOM 查询。它不访问网络页面或账号。需要手动验证本地
CDP 连接时，先打开 Chrome，再显式启用项目现有的集成测试：

```powershell
$env:MYBOT_RUN_BROWSER_INTEGRATION = "1"
.\.venv\Scripts\python.exe tests\test_browser.py
```

没有安装 `playwright-cli` 时集成测试会安全跳过。启用本地 Chrome 测试后会连接
真实浏览器，因此运行前应保存正在编辑的网页内容。

手动验证持久化浏览器时，可以让 MyBot 执行“打开一个新的托管浏览器并进入某
网站”，完成一次登录后关闭 session，再重复打开并检查登录状态是否保留。

## 扩展工具

新增浏览器工具时应继承 `PlaywrightCliTool`，注入 Registry 创建的共享
`BrowserSessionManager`，并提供 `name`、`description`、`parameters` 和异步
`execute()`。CLI 执行应返回 `BrowserResult`，然后在以下位置同步：

1. `mybot/tools/browser/__init__.py`
2. `mybot/tools/__init__.py`
3. `mybot/tools/registry.py`

新增启动方式时必须使用 workspace 内的受控持久化 profile，并继续禁止通过
`exec` 绕过结构化浏览器工具。
