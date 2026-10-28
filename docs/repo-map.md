# Repo Map v1

Repo Map 是按需生成的只读结构地图，不是业务说明、依赖安装器或运行时调用图。无需索引数据库、Embedding、后台扫描或模型请求。

## 使用

Web 沿用现有启动方式：

```sh
uv run python -m mybot.web --workspace /absolute/path/to/project --port 8765
```

在项目区域点击“查看项目结构”，打开可滚动的结构面板。默认不扫描；每次点击重新读取。显示扫描数、展示数、截断和不可读取提示，不展示宿主绝对路径、不编辑文件。项目仍由服务启动时确定，切换需重启。按钮调用经过原同源认证、Cookie、CSRF 和 CSP 保护的 POST `/api/repo-map`，只接受空 JSON 对象。任务忙碌、清理不确定或另一地图请求进行中时拒绝本次查看。

模型侧仅 `coding.enabled=true` 时通过原生 ToolRegistry 注册 `repo_map`，参数为 `{}` 或 `{"max_files": 40}`（1–120）。它属于只读能力；不会开启 Patch、命令权限或绕过审批。跨文件任务可先调用一次，再用 `search_code` / `read_file_range` 查看具体实现；普通聊天不会注册此工具，也不会自动增加调用。地图进入工具结果时与其他工具一样占用现有上下文预算。

## 输出示例（摘录）

对于已跟踪的 `pkg/main.py`：

```python
from .helper import answer
class App:
    def start(self): pass
```

以及 `pkg/helper.py`，结构记录为：

```json
{
  "path": "pkg/main.py",
  "status": "parsed",
  "symbols": [
    {"kind": "class", "name": "App", "line": 2, "name_truncated": false},
    {"kind": "method", "name": "App.start", "line": 3, "name_truncated": false}
  ],
  "imports": [{
    "kind": "from .helper",
    "names": [{"name": "answer", "alias": null}],
    "line": 1,
    "top_level": true,
    "targets": ["pkg/helper.py"],
    "resolution": "local_candidate"
  }],
  "symbols_imports_truncated": false
}
```

外层另有 `scanned_files`、`shown_files`、`skipped_files`、`truncated`、`tracked_only`、`static_only`、`index_incomplete` 与 `limits`。扫描数不包含受保护/被跳过路径，展示数可能因输出上限更小。非 Python 文件只显示相对路径及状态；不会读取正文。

## 事实与限制

- 使用 `git ls-files --cached -z`，只读取当前工作树中已跟踪文件，不读取 Index 内旧版本，不包含 untracked。复用 RepositoryTool 的只读 Git 设置，禁用可选 Index 写锁、hooks、fsmonitor 和已配置 filter，不执行构建脚本。
- 标准库 `ast.parse` 记录模块顶层普通/异步函数、顶层类及其直接普通/异步方法，行号为 AST 定义起始行（从1开始）。不解析方法体语义，不包含嵌套函数作为顶层符号。
- import/相对 import/别名从 AST 提取，包括嵌套作用域的语句；`top_level` 只说明语法位置，不证明执行过。按仓库相对路径建立有限模块映射，包对应 `__init__.py`。唯一候选标 `local_candidate`，歧义标 `ambiguous`，其他为 `external_or_unresolved`。不猜测 src 布局、sys.path、运行时条件、动态 import、属性与重导出。`from pkg import x` 可列包与子模块候选，不证明 x 必定是该子模块。
- 复用原路径及隐私规则：隐藏路径、secrets、真实 config/config.json、密钥、数据库、权重等不进入地图；另拒绝 credentials 前缀和 SQLite 扩展。所有符号链接路径（包括内部别名）均跳过，不跟随越界链接。不是任意内容的秘密检测器，普通源码中的命名仍可能含敏感信息；与原仓库工具一样，面对恶意并发改写不提供完整 OS 沙盒快照保证。
- 最多分析120文件，每文件512KiB。Git 输出最多64KiB且原有进程超时/清理机制继续有效。每文件最多64符号、64 import、每条最多64名称/目标，AST 遍历最多10,000节点；路径/名称最多256字符并编码控制字符与双向控制字符。解析失败单文件标 `parse_error`，不输出源码片段或异常正文。
- 总工具结果（含元数据序列化）最多12KiB；逐记录削减结构信息，保留合法 JSON，超限停止继续扫描。超限用 `truncated`，单文件用 `symbols_imports_truncated`/`path_truncated`，大小超限用 `file_too_large`。`index_incomplete` 表示截断或路径跳过，不能把未列出的依赖视为不存在。
- 不执行 import、第三方脚本、项目代码、测试命令，不修改工作区或 Git Index，不提供运行中切换项目。每文件是读取时观察，非整个仓库的原子快照。地图不会增加付费请求；模型主动调用工具后正常后续回复仍按原请求预算计数。

## 离线验证

```sh
uv run python -m unittest scripts.check_repo_map scripts.check_repository_tools scripts.check_patch_editing scripts.check_tool_authority scripts.check_web_ui scripts.check_provider_chain -q
uv run python -m compileall -q mybot scripts
node --check mybot/web/static/app.js
git diff --check
```

专项使用临时 Git 项目和 Mock Client，覆盖结构/行号、相对导入与歧义、解析失败、隐私/符号链接、120文件/512KiB/12KiB限制、不执行/不写文件、Coding 注册、AgentLoop 调用与无自动地图、认证及按需 Web 请求。真实模型请求为0。未运行完整 Benchmark、Canary 或付费兼容验证。
