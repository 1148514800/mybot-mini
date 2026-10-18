# Phase 23：Git-Aware Coding Workflow — 任务级审查与安全撤销

## 1. 学习目标与概念

本阶段在 Phase22 的自主编码闭环外增加任务级变更证据和宿主撤销入口。核心不变量是：只能撤销当前任务原生 Patch 产生、且当前版本仍可完整确认的变化。任务失败不会自动触发撤销；模型不能调用 Undo。

Git 有三个不同状态：HEAD 是当前提交，Index 是下次提交准备使用的暂存内容，Working Tree 是磁盘当前文件。三者可以不同。用户可能已暂存 README，继续修改源码，并有未跟踪笔记。整个 Git Diff 混合了这些工作，不能说明哪些是 Agent 刚刚产生的。

因此，Git Baseline 只提供任务开始的环境证据；Change Journal 保存任务首次 Patch 前的实际字节 A 与最后成功发布的字节 C。Agent-only Diff 是 A→C，Git Diff 则可能是 HEAD→Index 或 Index→Working Tree。Undo 是在严格前置条件下把 C 恢复成 A，绝不是恢复 HEAD。

Dirty 仓库可以局部编辑：Patch 依据当前完整 SHA 和唯一锚点，修改目标中的指定位置；Journal 的 A 包含用户原有注释。撤销恢复这个 A，自然保留用户注释。禁止用 reset、全仓 restore/checkout、clean、stash 代替这条证据链，它们可能覆盖未被本任务产生的工作。

## 2. 架构与调用关系

```text
AgentLoop.handle_message(普通任务)
  ├─ 关闭上一任务 Capsule
  ├─ 创建 Phase22 CodingTaskController
  ├─ 校验原生 Registry → GitBaseline.capture（首个模型请求前）
  ├─ ChangeJournal → 绑定 ApplyPatchTool.observer
  └─ 原 ReAct 循环
       ├─ 原生 Patch：预检查 → before_publish → Stage/Publish/验证/清理
       │                                  └─ 最终成功才 after_success
       │                                  └─ 最终失败则 on_failure
       ├─ RunCommandTool：原独立审批与 Seatbelt，原 Controller 验证
       └─ 结束：只读刷新状态 → 有界摘要 → 保留最近 Capsule
            finally：移除 Observer，不保存 Controller

/changes → 只读刷新 → 当前版本校验 → Journal A→C Diff
/undo → UndoService → 全批 Preflight → 独立批准 → 全批重检
      → Stage → 每文件重检/发布/验证 → 失败时有条件恢复 → 消费 Capsule
/clear、新普通任务、异常/取消 → 关闭并释放旧 Capsule
```

没有第二个 AgentLoop，没有模型 Reviewer，也没有新增 Git 写工具。Controller 负责预算、停止、修订与测试证据；Journal 负责原生 Patch 的来源和私有前后镜像；UndoService 只服务宿主 CLI。旧任务 Controller 和 Session 不能重新授权旧 Capsule。

## 3. 核心文件与函数

| 文件 | 职责和关键调用 |
| --- | --- |
| `mybot/agent/git_workflow.py`（新增） | Settings/严格配置校验；`GitBaseline.capture`；`GitMetadataScope.create/fingerprint`；固定路径安全读取 `read_scoped`；完整 Index 格式检查 |
| `mybot/agent/change_journal.py`（新增） | 不可变 `ChangeEntry`；`before_publish/after_success/on_failure`；`can_undo/check_entry`；摘要、Agent Diff 与 Capsule 生命周期 |
| `mybot/tools/undo.py`（新增） | `UndoService.undo/_preflight`；私有 `UndoTransaction` 复用 Patch 文件操作，新增受限 remove 和条件恢复 |
| `mybot/tools/undo_approval.py`（新增） | 冻结请求 `undo_request`、严格枚举 `authorize_undo`、交互式 `cli_undo_approval` |
| `mybot/tools/patch.py` | 仅增加可选内部 Observer；公开参数和 Schema 不变 |
| `mybot/agent/loop.py` | 最小接线、宿主 `/changes`/`/undo`、结束摘要、验证失效和释放 |
| `mybot/config.py`、`mybot/app.py` | 可选配置与独立 Undo Provider 注入 |
| `config/config.example.json` | 默认关闭的模板，不包含真实凭证 |
| `mybot/evaluation/git_workflow.py`（新增） | 反馈驱动合成策略、真实 Git/Patch/命令/Undo、事后 Gold 评分 |
| `evals/git_workflow_cases.json`（新增） | 16 个独立案例及评分预期 |
| `scripts/check_git_workflow.py`（新增） | 专项安全回归 |
| `scripts/evaluate_git_workflow.py`（新增） | 全部独立案例汇总 CLI |
| `scripts/git_workflow_demo.py`（新增） | 成功、外部冲突、拒绝三条动态路径 |
| `scripts/check_phase.py` | 全阶段回归入口加入新专项 |
| `README.md`、本学习文档、阶段索引、`AI_HANDOFF.md` | 使用说明、学习资料、当前状态 |

Phase19 RepositoryTool、Phase21 命令执行与 MCP Approval、Phase22 Controller 本体均保持原实现。

## 4. 配置与启动条件

默认模板 `enabled=false`、`undo_enabled=false`；关闭时不捕获 Git Baseline、不保存 Patch 镜像、不拦截新命令，也不改变 Registry、Schema、Session 与旧路由行为。

局部配置示例（合并进本地配置，其余模型字段另行配置）：

```json
{
  "coding": {
    "enabled": true,
    "patch_mode": "write",
    "command": {"mode": "macos_readonly"},
    "autonomy": {"enabled": true},
    "git_workflow": {
      "enabled": true,
      "undo_enabled": true,
      "max_files": 24,
      "max_journal_bytes": 8388608,
      "max_review_chars": 20000
    }
  },
  "mcp": {"enabled": false}
}
```

启用依赖 coding+write+autonomy；严格检查布尔、整数、上下限与未知字段。Undo 额外要求真实命令工具处于 macos_readonly、关闭 MCP、精确类型的默认 Patch-only Registry。不能靠名称或模型传来的 metadata 冒充原生工具。宿主工具注入未经支持的类型时，首个模型请求前阻止任务。

Workspace 必须恰好是可读 Git checkout 根目录；第一版保守拒绝嵌套子目录作为 Workspace。review-only 可以使用 host_confirm 或 MCP，但摘要必须指出外部副作用可能存在，且不能启用安全 Undo。

## 5. Baseline、Index 与 Git 只读边界

`capture` 复用 Phase19 GitStatusTool 与固定只读 runner：安全 Git 配置、禁用外部 diff/textconv/filter/hook 等执行路径、限制超时和输出，不引入模型可选 Git argv。捕获 HEAD、staged/unstaged/untracked/rename/conflict、截断和完整性。

普通仓库使用实际 `.git/index`。独立 Git Worktree 的 `.git` 是指针文件：先用安全 rev-parse 定位 admin/common，再验证 `.git`、admin/gitdir、commondir 的互相对应和目录身份。固定内部路径通过 dir_fd、O_NOFOLLOW 和普通单链接文件检查读取；不向模型开放 `.git` 任意读取，也不在摘要暴露内部绝对路径。Worktree 指针文件本身也纳入后续一致性校验。

Index 指纹包含完整有界字节 SHA256 和 inode/stat 版本，HEAD 与当前分支引用、packed-refs 同样固定读取比较。任务开始前后稳定、无截断/冲突才能 complete。缺 Index、损坏、权限不可用、未知布局均保守禁用 Undo；仍尽量展示只读状态。

第一版仅覆盖 SHA1 的完整 v2/v3 Index，验证 DIRC、条目边界、路径长度/填充、校验和和扩展。拒绝 v4、SHA256、split/shared index、sparse/extended flags、gitlink 子模块条目及未知必需扩展，避免把未覆盖的共享状态误判为完整。此处是本实现的支持范围，并非 Git 的限制；格式依据 [Git 官方 Index 规范](https://git-scm.com/docs/gitformat-index)。

不调用 git add/reset/restore 等写操作。任务中 HEAD/Index 或指针发生变化，后续受保护 Patch 和 Undo 都拒绝；即使内容恢复相同但版本改变也保守拒绝。Git status 只用于提示，不能充当全文件系统监视器。

## 6. Journal：准确来源、有界内存与隐私

每个 `ChangeEntry` 保存相对路径、原来是否存在、A/最终 C 的 SHA、原始模式、最终 stat 版本和受支持属性、首次/末次 Patch revision、基线用户 Git 状态；A/C 原始字节只在进程私有内存中，不参与 dataclass repr。

`before_publish` 接收真实 Prepared，而非 ToolResult。先验证旧 C→新 Patch before 的字节、完整 stat 和属性连续性；计算不同文件数与保留峰值字节预算，再准备私有 pending map。预算不够返回 `journal_budget_exceeded`，在 Stage/Publish 前拒绝，绝不先写后丢记录。

A→B→C 合并时只保留首次 A 和最新 C、首次/末次 revision。Agent add 后再 update 仍是 added；用户原有未跟踪文件被更新则是 updated，不能被删除。中间失败不提交成功记录。清理失败、回滚冲突或 Journal 最后提交失败标记执行不确定，不生成虚假的成功归属。

`after_success` 发生在整个 Patch 发布、最终检查和临时清理之后，读取当前文件确认 body、属性、模式及发布 inode，然后原子替换 Journal map。原始 A 早已在发布前取得；不能在写后猜测 A。最终 stat 用于下一次 Patch 与 Undo 的严格版本前置条件。

默认 24 文件、8MiB 镜像、20,000字符审查。配置允许字节上限至16MiB，但 Patch 原有单次/单文件/UTF8 限制仍然有效。镜像预算不代表 Python 总进程 RSS、diff 对象或原 Patch 临时缓冲的硬内存配额。

原始镜像不会放进 metadata、SessionStore、调试日志、普通任务摘要或磁盘快照。用户显式 `/changes` 才展示差异；Diff 可能含源码，应在可信终端查看。CLI 结果不追加到 Session。原有 Patch 工具输入/反馈和用户本来发给模型的内容仍遵守原机制，不能将“私有 Journal”理解成模型从未看过源码。

Capsule 只保留最近任务，`/clear`、新普通任务、异常/取消会释放。进程重启、旧 Session 和旧验证文字不恢复撤销能力。成功 Undo 或发生发布尝试后消费 Capsule；否决不缓存批准，每次都重新预检和审批。

## 7. `/changes` 与 Agent-only Review

用户输入 `/changes` 由宿主拦截，不调用模型、不注册工具。输出摘要包含 native_patch 来源、updated/added、preexisting Git 状态、前后 SHA、当前匹配与 stale_review、baseline 完整性、其他 Git 变化与 Undo 资格。

默认任务回复只加 `[TASK CHANGE SUMMARY]` 有界 JSON，无正文 Diff。`/changes` 才通过 difflib 生成首次 A→最后 C unified diff，added 的旧路径为 `/dev/null`。控制字符/方向字符和路径转义，保持无末尾换行提示。超长摘要列表裁剪并标 `review_truncated`；超长 Diff 明确省略，不能暗示已完整审查。

当前版本不匹配时展示的是带 stale 标记的历史任务差异，并撤销旧 verified 结论。其他路径只能标 `preexisting_user_or_external` 或 `unknown_external`，绝不能因当前 Git Diff 中出现而认领。

## 8. `/undo`：独立审批与完整前置条件

宿主顺序：检查 Capsule/完整 Baseline → 所有目标完整 Preflight → 释放此次预检临时对象 → 显示冻结请求 → 明确批准 → 再次检查 Capsule 和完整请求相等 → 所有目标再次 Preflight → Stage → 发布前逐一重检 → 发布后验证。

审批列出完整相对路径、restore/remove_added 动作、当前最终 SHA 和目标原始 SHA（新增文件目标为 null），不含正文。请求超限或含无法安全展示的敏感路径时拒绝；Provider 缺失/异常、布尔 True、DENY、非 TTY、非精确小写 yes 都不批准。复用 ApprovalDecision 枚举，但独立于命令/MCP 授权，不缓存、不借用模型文字。

每个目标必须仍是安全普通单链接文件、父目录身份未变、没有符号链接穿越、内容/完整 stat/inode/模式/属性符合 C；HEAD、实际 Index 及指针也必须仍一致。审批后用户改任一目标或暂存新增文件，就整批拒绝，无目标被写入。无关普通笔记变化可以保留并展示，不参与 Undo。

## 9. 多文件发布、恢复与竞争限制

update 使用原 Patch 的同目录 Stage、fsync、发布前版本检查和单文件 replace。added 只删除 Journal 证明由本任务创建且无人接管的那个文件，绝不清目录或删除用户原有 untracked 文件。

最多24文件先全部预检，再全部 Stage，再发布。失败时逆序有条件恢复：只有当前仍是本次发布结果才能恢复；已撤销删除的新增文件通过已验证备份和 no-clobber link 重新创建，目标出现则不覆盖；检查备份 inode/模式/属性和恢复后身份。清理只操作已记录的临时 inode。恢复确认完成返回 `undo_rolled_back`；并发变化或无法确认返回 `undo_partial_failure_possible` 并保留外部内容，不虚称整批无变化。

状态还包括 unavailable/available/previewed/approved/completed/conflict/denied。结果只有路径、前后 SHA、Index 是否一致、批准/冲突/失效等元数据。

TOCTOU 无法完全消除：POSIX 普通 replace/unlink 没有“匹配此 inode 才修改”的通用原子 CAS；最后检查与系统调用间仍有竞争窗口。这里沿用 Phase20 的重复校验和条件恢复，不宣称抵抗同权限恶意竞争，也不宣称跨文件崩溃原子性。没有持久事务日志或崩溃后自动 Undo。

## 10. 验证失效与边界

Undo 成功会把当前宿主报告改为 `edited_unverified`、verification invalid、通过测试数清零，revision 前进；不确定发布为 execution_uncertain。提示“此前修复的测试记录不再适用于当前内容；未自动复测”。审批拒绝且文件无变化时保留原验证。冲突说明文件或 Git 证据已改变，也使旧 verified 失效。

`/changes` 后的外部变化检查和下一个普通任务的新 Controller 都不采信旧 Session 验证。历史对话可以保留历史事实，当前宿主状态不会把它当新证据。

macos_readonly 命令沿用 Phase21 真实每次审批与 Seatbelt，不能提供额外可写来源。host_confirm 只是批准后的宿主命令，没有 OS 隔离，review-only 摘要标外部副作用；MCP metadata 不能证明来源。启用 Undo 时拒绝 MCP/额外可写工具。不扩大 Skills、网络、Git 或模型授权。

## 11. macOS、Python 3.12+、uv 实操

```bash
uv sync --frozen
uv run python -m compileall -q mybot scripts
uv run python -m scripts.check_git_workflow
uv run python -m scripts.check_phase
uv run python -m scripts.git_workflow_demo
uv run python -m scripts.evaluate_git_workflow
uv run python -m scripts.check_repository_tools
uv run python -m scripts.check_patch_editing
uv run python -m scripts.check_command_execution
uv run python -m scripts.check_autonomous_coding
uv run python -m scripts.compare_tool_discovery
uv run python -m scripts.compare_tool_retrieval
uv run python -m scripts.compare_adaptive_routing
uv run python -m scripts.compare_selective_routing
uv run python scripts/test_phase_archives.py
# 交互使用另行复制模板并填写本地凭证：
cp config/config.example.json config/config.json
uv run python mybot/main.py
```

交互启用时还要将本地 `workspace.path` 设为目标 Git checkout 的绝对根目录，模板的 `./workspace` 并非该根目录，直接启用会被拒绝。不要向版本库提交真实 config/config.json。真实模型交互不属于离线验证。

动态 Demo 创建临时 Git 仓库：源码含减法教学 Bug 与用户未暂存注释，README 已暂存，notes.txt 与测试夹具未跟踪。反馈驱动策略先读取/测试，真实命令 exit1，再原生 Patch 修正并新增 tests/regression.py，再测试 exit0。工作由原 AgentLoop 完成，Gold 不提前给策略。

实际 `/changes` 摘要摘录（省略随机 HEAD 和完整 SHA）：

```text
Task Change Review (Agent Diff is not Git Diff)
agent_owned_files: 2
preexisting_user_dirty_files: 4
src/calculator.py: updated, preexisting=modified, current_matches=true
tests/regression.py: added, current_matches=true
baseline.staged: [README.md]
baseline.untracked: [notes.txt, tests/test_unittest_calculator.py]
undo_eligible: true
--- a/"src/calculator.py"
+++ b/"src/calculator.py"
-    return left - right
+    return left + right
--- /dev/null
+++ b/"tests/regression.py"
+import unittest
+from src.calculator import add
+...
```

这里用户注释在 A 与 C 中相同，不成为 Agent 新增行；完整文件恢复时仍保留它。Demo 的正常路径 `undo_completed`，恢复源码原始字节并删除新增回归文件，README/notes/Index 不变。用户并发追加注释路径 `undo_conflict` 且整批不写。Provider 拒绝路径 `undo_denied` 且不写。

16-case Evaluation 覆盖 clean/dirty、多文件新增、多次 Patch、外部编辑、同字节替换、Index/HEAD 变化、拒绝、clear/restart、发布失败回滚、预算、无关变化、MCP伪造、并发恢复不确定。预期 Gold 只在实际动作后评分；不以模拟字典代替文件操作。统计源码全文件前后、用户数据与 Index，确认工具ID配对、CLI无额外模型请求。故意造成的不确定路径按保留并发用户数据的安全预期评分，并非声称撤销成功。

## 12. 验证记录、常见问题与阶段变化

实测环境为 macOS、Python3.12+、uv；所有命令优先 uv run，未访问真实模型或第三方服务。

| 检查 | 结果 |
| --- | --- |
| Git Workflow 专项 | 101/101；包括 Worktree 指针、split/v4 Index、同字节 inode 替换、Journal 最后提交、取消/异常释放与独立评测、评分器检测额外意外文件 |
| Phase19 Repository / Phase20 Patch | 34/34、55/55 |
| Phase21 Command / Phase22 Autonomy | 58/58、80/80；真实 Seatbelt 测试通过 |
| 独立 Evaluation | 16/16 符合安全预期；5完成撤销、4冲突、1拒绝、1部分失败、1预算拒绝，其余生命周期/回滚/伪造等预期结果 |
| 独立三路径 Demo | 3/3；成功/外部冲突/拒绝 |
| 归属与数据保护 | false_owned_changes_count=0；unintended_file_changes_count=0；Index保留16/16；验证失效11例 |
| 配对与调用 | 全例工具ID配对；/changes与/undo无额外模型请求；Token与费用null |
| 编译与文件扫描 | mybot/scripts编译通过；无凭证格式、真实配置、Session、缓存或大文件；原main用户文件/Index及全部旧Tag/ZIP哈希不变 |

Evaluation 累计28项 Agent文件记录、60项任务前Dirty记录；它们是跨案例汇总，有重复夹具路径，不是28/60个独立仓库文件。Index/HEAD外部变化案例有意由夹具改变 Git 元数据，`index_preserved_count` 指 Undo 没有进一步改变用户当时的 Index；正常成功路径也等于任务起始 Index。

四组基准与 Phase22 分支 e117fd9 的实跑结果逐字段相同，只排除 task_wall_time_seconds/request_latency_seconds/request_latencies_seconds/routing_overhead_ms/git_commit/worktree_dirty 六个字段：

| 旧基准 | 结果 |
| --- | --- |
| Discovery：3案例 | Eager7请求/409199 Schema字符；Progressive15/52280；任务均成功 |
| Retrieval：36案例 | Recall@5 Literal57.8125%、BM25 62.5%、Hybrid87.5%；负例4/4正确 |
| Adaptive：12案例 | Eager25请求/1461425字符，Progressive51/175363，Adaptive25/176425；均12/12成功 |
| Selective：60路由案例 | precision88.8889%、recall97.2222%；负例24/24正确；多工具全覆盖10/12 |
| Selective任务 | 核心12例27请求/137582字符；挑战10例23/109693；最终成功，原有路由遗漏仍保留 |

归档脚本集成测试已通过：不可覆盖、只还原独立目录、缺失/恶意ZIP、Session/密钥/缓存拒绝及不可变修订测试。Phase1～23全量750/750（原649+新101）及Phase1/2原断言通过，退出码0；先前一次进程在编辑中启动导致旧类/新测试混用，已以最终实现重跑通过，未把该失败计为完成。正式归档与独立解压/还原的已完成事实见第13节；本节源验证结论不变。

- `/undo` unavailable：检查显式配置、原生工具模式、有效 checkout 根目录、完整 Index 支持范围、Capsule 生命周期；不要通过绕过检查强行撤销。
- conflict：先人工查看目标与 Git 状态；没有自动 reset 或清理建议。
- 只看到摘要：输入 `/changes` 获取显式 Diff；它也可能因上限而截断。
- 非交互 Demo 为何能批准：测试注入只用于一次性合成仓库的独立枚举 Provider，真实 CLI 非TTY仍拒绝。
- macOS 沙盒不可用：沿用 Phase21 阻止执行，不降级成无隔离安全承诺。

Phase22→23 增加 Baseline/Journal/Capsule/宿主 Review 与 Undo；原预算、修订绑定测试、每条命令授权和失败反馈闭环保留。下一阶段若开展 Coding Agent Evaluation，需继续使用独立 Gold、真实文件/测试证据、误归属/误覆盖指标，区分合成策略安全验证与真实模型能力。尚未运行真实 LLM、第三方 MCP/OAuth，没有实际 Token/费用；二者均 null。

阶段不自动进入24，不 Push/Merge。以下发布记录属于后续纯文档提交，未修改功能源或移动 Tag。

## 13. 正式归档与独立还原记录

- 实现/归档源提交：`edda5426534eaffe1ffb303f69fb855a9ebe482e`，19文件变更；源工作树干净，`save_phase.sh 23` 对确切提交导出并再次冻结安装、编译、750全量通过后创建唯一 annotated `phase-23`。
- Tag对象：`58e43675638404da2f851f91856b83e74922a6df`，始终指向上述源提交。本记录后补，未移动Tag或重导出旧ZIP。
- 正式ZIP：`/Volumes/move-disk/data/code/mybot-mini-snapshots/phase-23.zip`。
- 脚本默认ZIP：`/Users/godblack/.codex/worktrees/phase-23/mybot-mini-snapshots/phase-23.zip`；通过独占创建不可覆盖复制到正式位置，SHA256均为 `96d546cc1db18be067299b93b4cc3a805de053371d62d77f637aca5c1e069626`。
- ZIP：183 entries / 164 files；CRC、安全路径/敏感内容校验、ZIP注释提交SHA、清单及每文件字节与Tag一致；没有._文件。
- 正式ZIP独立APFS解压：`/var/folders/7p/n7p6_hdd08j48k1kbg6kjnvh0000gn/T/mybot-phase23-official-zip-40s6vqiw/source`。
- `bash scripts/restore_phase.sh 23` 独立学习目录：`/Users/godblack/.codex/worktrees/phase-23/mybot-mini-learning/phase-23`；未切换当前开发分支。
- 两个副本均 `uv sync --frozen`、编译mybot/scripts、750全量及原断言、四组旧基准、16例Evaluation、3例Demo通过；四基准与Phase22除六字段逐字段一致。测试后164个源文件哈希仍与Tag一致。
- 两个副本均false_owned=0、unintended=0、Index保留16/16；没有真实LLM/第三方服务、真实配置或Session文件。
- 原main仍3461dc7，用户app.py/USER.md和原Index哈希不变；旧23个Tag对象及全部旧ZIP（含已有AppleDouble）哈希不变。只新增phase-23；未Push/Merge/进入24。

复习：`cd "/Users/godblack/.codex/worktrees/phase-23/mybot-mini-learning/phase-23"`，执行第11节离线命令即可。APFS临时解压用于核验，长期学习使用restore目录。不要将临时目录视为永久备份。ExFAT可能自行生成AppleDouble；导出不含它们，复制设置COPYFILE_DISABLE=1，不承诺操作系统永不生成。

当前保守边界还包括：尚无提交的仓库、非ASCII/未支持分支名、特殊Git布局或完整Index无法确认时禁Undo；无原子inode条件replace/unlink、跨文件崩溃事务、完整外部副作用监视和进程总内存硬配额。Seatbelt弃用及原Phase21资源/后代进程回收边界不变。下一阶段评测可在明确新任务后开展，本阶段无关键未完成项。

archive-ready: true
