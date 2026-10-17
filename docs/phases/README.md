# Phase 学习索引

每个 Phase 使用不可移动的 Git Tag 保存完整已提交源码，同时导出同级目录 `../mybot-mini-snapshots/phase-XX.zip`。ZIP 不提交；丢失时可从 Tag 再次执行 `git archive` 导出，不能重新创建同名 Tag。

| Phase | 学习主题 | 状态 | Git Tag | 学习文档 |
| --- | --- | --- | --- | --- |
| 01 | Agent Tool Calling 可观测化 | 已验证，归档本次补齐文档的提交 | `phase-01` | [phase-01.md](phase-01.md) |
| 02 | 自定义工具 `list_files` | 已验证，独立归档 | `phase-02` | [phase-02.md](phase-02.md) |
| 03 | Session 多轮对话 | 已验证，独立归档 | `phase-03` | [phase-03.md](phase-03.md) |
| 04 | 可选任务规划 DIRECT / PLANNED | 已验证，独立归档 | `phase-04` | [phase-04.md](phase-04.md) |
| 05 | Session JSON 持久化与恢复 | 已验证，独立归档 | `phase-05` | [phase-05.md](phase-05.md) |
| 06 | Context 字符预算与请求压缩 | 已验证，独立归档 | `phase-06` | [phase-06.md](phase-06.md) |
| 07 | 本地 Agent Skills 渐进加载 | 已验证，独立归档 | `phase-07` | [phase-07.md](phase-07.md) |
| 08 | 隔离 Agent Evaluation 与 Skills A/B | 已验证，独立归档 | `phase-08` | [phase-08.md](phase-08.md) |
| 09 | Evaluation 2.0 独立指标与 Off/Auto/Guided | 已验证，独立归档 | `phase-09` | [phase-09.md](phase-09.md) |
| 10 | 本地 stdio MCP Client 与外部工具 | 已验证，独立归档 | `phase-10` | [phase-10.md](phase-10.md) |
| 11 | MCP 工具权限与 Human-in-the-Loop | 已验证，独立归档 | `phase-11` | [phase-11.md](phase-11.md) |
| 12 | MCP Streamable HTTP 与多传输管理 | 已验证，独立归档 | `phase-12` | [phase-12.md](phase-12.md) |
| 13 | MCP Bearer认证与HTTP响应接收安全 | 已验证，独立归档 | `phase-13` | [phase-13.md](phase-13.md) |
| 14 | MCP OAuth授权码与PKCE、内存刷新 | 已验证，独立归档 | `phase-14` | [phase-14.md](phase-14.md) |
| 15 | MCP工具目录、检索与渐进披露 | 已验证，独立归档 | `phase-15` | [phase-15.md](phase-15.md) |
| 16 | BM25/双语检索与独立Agent评测Harness | 已验证，独立归档 | `phase-16` | [phase-16.md](phase-16.md) |

## 保存一个新阶段

1. 阅读代码和 Git 历史，完成阶段功能并运行真实有效的测试。
2. 学习文档按 Phase 01 的十项结构编写，记录实际结果与未验证部分。仅完成验证后加入独立一行 `archive-ready: true`。
3. 更新本索引与 `AI_HANDOFF.md`，检查 diff，只提交本阶段文件；当前提交必须包含本阶段文档。
4. 在干净工作区执行：

```bash
bash scripts/save_phase.sh 2 "自定义 Agent 工具 list_files"
```

脚本不自动 commit。它检查文档、已有 Tag、ZIP 和工作区，先对 HEAD 的 ZIP 独立解压，执行 `uv sync --frozen`、编译及离线回归检查，再发布 ZIP 和创建 annotated Tag。额外的阶段专用测试由开发者先运行并记录到文档；通用检查不能证明所有新功能。敏感文件名和常见密钥格式会被拒绝，提交前仍须检查任意其他凭证与大文件。归档仅包含已跟踪文件，不包括本地真实配置和环境。

如果 ZIP 发布后创建 Tag 失败，ZIP 会保留；先核对原因和提交 SHA，手动恢复或移走该 ZIP，脚本不会覆盖文件，也不会强制移动 Tag。Tag/ZIP 都是本地文件，永久保存仍需另行备份；默认不 push。

## 独立复习

```bash
bash scripts/restore_phase.sh 1
cd ../mybot-mini-learning/phase-01
uv sync --frozen
cp config/config.example.json config/config.json
# 编辑本地 API 凭证
uv run python mybot/main.py
```

优先使用 Tag；找不到 Tag 时使用同级快照。还原到独立目录，默认拒绝覆盖，完全不 checkout 当前分支。ZIP 检查 CRC、必要文件、路径穿越、符号链接及敏感文件。ZIP 来源必须可信，校验结构不等于证明来源。仅有 ZIP 时没有 Git 历史。离线复习可执行 `uv run python -m scripts.check_phase`。

macOS ExFAT 会自行生成 `._*` 元数据文件，脚本通过 `git archive` 避免带入未跟踪文件，并设置 `COPYFILE_DISABLE=1` 减少复制元数据；系统仍可能生成。独立验证使用系统临时目录，以避开 ExFAT。建议学习目录位于 APFS。
