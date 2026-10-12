# Phase 02：自定义 Agent 工具 list_files（待完成）

## 真实状态

本地存在未提交 `mybot/tools/list_files.py`，以及 `mybot/tools/registry.py`、`mybot/agent/context.py` 的关联改动。未确认测试通过、未提交、没有 Tag 和 ZIP。本次归档体系建设保留这些文件，不将其混入 Phase 01。

## 安全补全方案

下一次明确进行 Phase 02 时先读取实际工具实现，核对路径边界、目录不存在、文件/目录区分、符号链接和返回格式；验证注册的 JSON Schema、真实工具执行和模拟模型循环。完成后按 Phase 01 的十项学习结构重写本草稿，记录实际测试，更新索引和交接并提交，再执行 `bash scripts/save_phase.sh 2 "自定义 Agent 工具 list_files"`。

不得仅凭存在源文件声明完成，不得提前添加 archive-ready 标记。本草稿不是完整阶段教程。
