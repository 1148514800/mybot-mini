# AI Handoff

## 当前目标与状态

已建立 Phase 学习归档体系；Phase 01 为已提交的 Tool Calling 可观测化（配置布尔字段 debug 控制），补齐学习文档并准备唯一 phase-01 Tag/ZIP。Phase 02 的 list_files 仅存在于工作区，未验证、未提交、未归档。本任务不进入 Phase 03。

## 实现与决策

- docs/phases/：索引、Phase 01 十项完整教程、Phase 02 真实状态草稿。
- scripts/save_phase.sh、restore_phase.sh：干净已提交版本保存、独立目录还原、防覆盖；共用参数、ZIP 校验及离线回归辅助脚本。
- AGENTS.md：永久 Phase 工作流，默认本地 commit/tag/ZIP，不 push。
- git archive 仅导出已跟踪版本；ZIP 在同级 mybot-mini-snapshots，学习目录在同级 mybot-mini-learning，不提交真实配置。
- 保存先独立解压、uv sync --frozen、compileall、离线测试，再发布 ZIP/Tag；archive-ready 标记是开发者验证声明，阶段专用测试仍必须运行。

## 验证

- bash -n：通过。
- 临时仓库集成测试：保存、Tag 还原、ZIP 单独还原、拒绝脏工作区/重复 Tag/重复 ZIP/已有学习目录/非法编号/缺失版本/恶意路径均通过；当前 HEAD 不受还原影响。
- 独立源码目录 uv sync --frozen、compileall、离线模型和文件工具回归：通过。
- 真实模型 API 未验证；需要用户凭证，不以模拟结果宣称线上成功。

## 环境与已知问题

使用 macOS/zsh、Python 3.12+、uv；启动 uv run python mybot/main.py。debug 在 config/config.json 顶层，默认 false，修改后重启；不读取 MYBOT_DEBUG。

ExFAT 会生成 ._* AppleDouble，复制尽量 COPYFILE_DISABLE=1 或 cp -X，不能保证系统不再生成；归档排除这些文件，独立验证使用 APFS 临时目录。

保留用户原有未提交修改：mybot/app.py、mybot/agent/context.py、mybot/tools/registry.py、mybot/tools/list_files.py。本任务未纳入提交或 Phase 01。敏感配置不输出、不提交；ZIP 文件名和常见凭证检查不能替代人工审查所有秘密。

## 下一步与不要重复

完成并验证 Phase 02 后重写 phase-02.md，更新索引/交接，提交，再运行 bash scripts/save_phase.sh 2 "自定义 Agent 工具 list_files"。不要给未提交代码打 Tag，不要覆盖 phase-01，不必重建归档架构。历史学习内容放 docs/phases 和 Git，本文件只保留当前状态。
