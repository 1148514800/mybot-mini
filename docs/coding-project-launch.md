# 真实项目 Web 启动入口

在 mybot-mini 代码目录运行；凭证始终读取该安装目录的 `config/config.json`，不是目标项目中的配置文件。

```bash
uv run python -m mybot.web --check --workspace /absolute/path/to/project
uv run python -m mybot.web --workspace /absolute/path/to/project --port 8765
```

也可省略 `--workspace`，使用现有 `workspace.path`。选择的目录必须已经存在、可访问，并且是 Git 工作树的根目录；默认配置目录也不会自动创建或 git init。显式参数要求绝对路径（支持展开 `~`）；规范化别名和符号链接到真实路径，子目录、普通非 Git 目录、损坏仓库和不可访问路径被拒绝。支持 linked worktree、detached HEAD 和尚未提交的正常 Git 仓库；原 Git-aware Controller 仍可能要求已有提交，不会自动提交。

## 预检与界面

`--check` 返回 JSON 和退出码：成功0，失败2。输出默认 Provider、声明顺序回绕后的切换链、规范化工作区、项目/分支、Coding、Patch、Receipt、file_access、RunCommand模式及是否需要审批。只检查本地配置字段，不验证远端 Key 是否有效，`provider_connection_tested=false`。不会启动 WebRuntime/SDK、请求模型、打开 Session DB、获取工具批准或执行项目代码。

配置缺失为 `CONFIG_NOT_FOUND`；JSON 语法错误为 `CONFIG_JSON_INVALID` 并给出1起始行号/列号，例如：

```json
{"ok": false, "error_type": "CONFIG_JSON_INVALID", "line": 29, "column": 5}
```

没有完整解析器错误、原始配置片段或凭证明文。默认项不存在为 `DEFAULT_PROVIDER_MISSING`；缺失/占位凭证、无效URL或模型字段为 `PROVIDER_FIELDS_INVALID`。URL要求HTTP(S)且不包含用户名/密码；不输出 Key 或真实 base_url。检查 Provider 顺序/字段复用 Failover Chain 的纯配置函数，不构造或调用 Client。

Git检查使用现有有界只读 runner和原生 Git filter抑制，禁用hooks/fsmonitor/可选Index写锁，不执行项目filter或初始化代码。Git状态可脏，不要求干净；超时、输出超限或损坏Index会明确拒绝，不自行修复。预检不是对未来并发修改的安全证明；运行时仍使用原 WorkspaceLease、工具路径边界、Receipt、Controller和审批检查。

启动后的侧栏和设置展示项目名、Git启动分支和Coding/Patch状态；不向普通SSE暴露完整宿主路径或配置。工作区固定到本进程，网页消息没有workspace字段/切换端点，模型工具不能选择新的根目录。切换项目需停止自己的服务后用新参数启动。现有Cookie/CSRF/CSP边界保持。

## 明确开启写入

`--workspace`不增加权限。若需Coding写入，请由用户在本地配置中明确设置，例如保留其他配置并合并：

```json
{
  "coding": {
    "enabled": true,
    "patch_mode": "write",
    "file_access": "read_only",
    "preview_receipt": true,
    "command": {"mode": "macos_readonly", "timeout_seconds": 30},
    "autonomy": {"enabled": true},
    "git_workflow": {"enabled": true, "undo_enabled": false}
  }
}
```

这只授权现有原生Preview/Receipt/Patch机制；普通文件访问仍只读。每次真实测试命令都要用户本人通过WebApproval，原macOS Seatbelt自检、路径/超时/输出限制继续有效。关闭Coding时沿用原只读/默认工具行为；在本项目入口不会给目标仓库生成instructions目录或种子文件。会话数据仍按原配置保存在项目外；拒绝Session数据库指向项目内部。

## 本轮验证

新增24个离线测试，相关专项共125项通过：默认/覆盖、非法路径、linked/detached/unborn/损坏Git、filter不执行、JSON行列、不泄漏凭证、check不启动服务/SDK、只读源码工具调用、消息禁止切换、无初始化副作用、Lease互斥和原Patch审批；Provider Chain及Streaming兼容专项通过。另有Python编译、JS语法和diff检查。所有模型均为Mock，真实请求0；无Canary、冻结或完整Benchmark，旧C01/C02资产、main、Tag和ZIP不修改。
