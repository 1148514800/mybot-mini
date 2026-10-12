# AGENTS.md

## 项目说明

本文件定义所有 AI 编程智能体在本仓库中工作时需要长期遵守的规则。

代码仓库、Git 历史以及项目文档是项目状态的事实来源。

GitHub 仓库：`mybot-mini`（`https://github.com/1148514800/mybot-mini`）。

---

## 每次会话开始

开始新的开发会话时，必须：

1. 阅读 `AGENTS.md`。
2. 如果存在，阅读 `AI_HANDOFF.md`。
3. 执行：

```bash
git status
git log -5 --oneline
```

4. 修改代码之前先阅读相关实现。
5. 优先从 `AI_HANDOFF.md` 的 `下一步` 继续开发。

除非确有必要，不要一开始扫描整个仓库。

---

## 开发规则

修改代码前：

1. 理解当前实现。
2. 搜索已有实现及其调用位置。
3. 尽可能复用现有抽象。
4. 不要重复创建已有模块、接口、工具类或抽象层。
5. 除非有明确理由，否则不要随意改变现有架构。

优先进行小范围、明确的修改，避免不必要的大规模重构。

---

## Git 工作流

开始开发前执行：

```bash
git status
git log -5 --oneline
```

完成一个独立任务后：

1. 运行相关测试。
2. 更新 `AI_HANDOFF.md`。
3. 检查代码修改：

```bash
git diff
git status
```

4. 提交当前任务：

```bash
git add <相关文件>
git commit -m "<type>: <清晰的修改说明>"
```

推荐 Commit 类型：

* `feat:` 新功能
* `fix:` Bug 修复
* `refactor:` 重构
* `test:` 测试
* `docs:` 文档
* `chore:` 维护工作

除非用户明确要求，否则不要自动执行 `git push`。

不要提交：

* 密钥
* Token
* `.env` 中的敏感信息
* 大型数据集
* 模型权重
* 临时文件
* 自动生成且不需要版本管理的文件

---

## 测试规则

修改代码后：

1. 优先运行与修改内容直接相关的最小测试。
2. 最小测试通过后，再运行更大范围的相关测试。
3. 如果关键测试仍然失败，不要宣称任务已经完成。

重要测试结果需要记录到：

`AI_HANDOFF.md`

---

## AI 交接

`AI_HANDOFF.md` 用于记录当前开发状态。

完成一个有意义的开发阶段后，需要更新：

* 当前目标
* 当前状态
* 已完成内容
* 修改文件
* 架构决策
* 测试结果
* 已知问题
* 下一步
* 不要重复进行的工作

保持内容简洁。

不要记录：

* 完整聊天历史
* 大量原始日志
* 冗长 Debug 过程
* 已经过时的方案

---

## 上下文管理

不要把聊天历史作为项目主要记忆。

项目状态的优先级：

1. 当前代码
2. Git 历史
3. `AGENTS.md`
4. `AI_HANDOFF.md`
5. 架构和技术决策文档

当聊天上下文越来越长时，应把重要信息写入项目文档，而不是一直依赖旧聊天记录。

---

## 安全规则

不要泄露或提交：

* API Key
* 密码
* Token
* 私有凭证
* `.env` 密钥

执行以下危险操作前必须询问用户：

```bash
git reset --hard
git clean -fd
git push --force
rm -rf
```

---

## 完成标准

一个任务只有满足以下条件才算完成：

* 功能实现完成
* 相关测试通过
* 已检查 `git diff`
* 已更新 `AI_HANDOFF.md`
* 已完成 Git Commit
* 剩余问题已经记录


---


## AI_HANDOFF 维护规则

`AI_HANDOFF.md` 是当前状态快照，而不是开发日志。

更新时：
- 删除已经失效的信息
- 合并已经完成的事项
- 不持续追加历史记录
- 不记录详细开发过程
- 历史修改通过 Git 查询
- 尽量保持文件简短，只保留下一位 Agent 继续工作所需的信息


---

## Phase 学习归档规范

此规范适用于以后每个 Phase，会话无需用户重复说明。环境使用 macOS/zsh、Python 3.12+、uv；运行和测试优先使用 `uv run`，CLI 命令为 `uv run python mybot/main.py`。

1. 开始阶段时检查 `git status`、`git log -5 --oneline`、`git tag -l`，以代码和 Git 为事实来源，不假设讨论过的功能已经完成。
2. 完成代码及阶段相关测试，不能将未完成或测试失败的 Phase 标记为完成，不擅自进入下一 Phase。
3. 自动更新 `docs/phases/phase-XX.md`，完整说明学习目标、Agent 概念、架构流程、核心文件、关键函数原理和调用关系、新增修改、macOS+uv 安装运行测试命令、实际案例与结果、常见问题、与上阶段变化。不能只写修改记录，不删除其他 Phase 学习资料。
4. 更新 `docs/phases/README.md` 索引、主题、真实状态和 Tag；验证完成后在阶段文档添加独立一行 `archive-ready: true`。
5. 更新 `AI_HANDOFF.md` 当前状态，历史学习记录只放 docs/phases 和 Git。检查 diff/status，仅提交本阶段相关文件，创建清晰 commit；当前提交应包含本阶段文档。其他未完成改动保留，不混入提交。
6. 从干净的已提交版本运行 `bash scripts/save_phase.sh XX "阶段名称"`，创建唯一 annotated Tag `phase-XX`，通过 git archive 导出同级 `../mybot-mini-snapshots/phase-XX.zip`，不把 ZIP 提交到 Git。工作区有其他未提交任务时可在干净独立 worktree 或临时克隆中归档该确切提交，不修改用户现有文件。
7. Tag 或 ZIP 已存在时先检查历史并报告冲突，禁止强制覆盖或移动 Tag。禁止归档未提交的代码。历史阶段无法准确还原时只报告事实与补全方案，不对最新代码冒充旧阶段，不改写历史。
8. 检查全部已跟踪文件，禁止包含密钥、Token、密码、真实 config/config.json、.env、.venv、缓存、临时文件及不必要大文件。脚本检查只是辅助，不能替代提交前内容审查。
9. 验证 ZIP 可独立解压，至少包含完整 mybot、pyproject.toml、uv.lock、配置模板、对应阶段文档。独立目录执行 `uv sync --frozen`、`uv run python -m compileall -q mybot` 和阶段测试。真实 API 缺少凭证时明确标注未验证，不能伪造成功。
10. 通过 `bash scripts/restore_phase.sh XX` 还原到独立学习目录，禁止改变当前开发分支，默认禁止覆盖已有目录。
11. 完成标准包括学习文档、索引、验证、交接、Commit、唯一 Tag、完整 ZIP 及独立还原验证；默认仅本地操作，不执行 git push。

用户要求尽量避免 `._*`：ExFAT 上 macOS 可能自动生成 AppleDouble；复制时使用 `COPYFILE_DISABLE=1` 或 `cp -X` 减少元数据，不承诺完全阻止。归档不包含这些文件，优先在 APFS 临时目录验证。
