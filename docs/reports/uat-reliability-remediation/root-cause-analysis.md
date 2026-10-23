# 根因复核

本任务基线为 codex/real-user-task-uat 的 a847884568184fcf5317d11ecfd0ec9a721b9db0（本地及远程核对一致）。本轮只做 OFFLINE/SYNTHETIC 工程修复，不是新 Phase、不创建或移动 Tag/ZIP，不重跑历史六例。

| 证据 | 确认根因 | 修复与边界 |
| --- | --- | --- |
| U04 Preview preflight/metadata_changed | 历史文件 uid501/gid0，进程 euid501/egid20；原 check_metadata 拒绝 unsupported_ownership | 新建 v2 Fixture 后使用原生 Preview 与真实元数据检查；旧 Fixture 不动、安全条件不变 |
| U05 首次 Patch 未成功 | 历史参数、原始错误未保留，具体类别 unknown | 新诊断用于未来调用，不回填历史、不套用 U04 根因 |
| U06 第5轮合法引用放不进主请求 | 原实现未在摘要调用前计算可用摘要空间 | 先由实际主请求剩余预算规划，再动态约束输出及有限删项 |
| U06 第6轮 length/不完整JSON | 固定1200上限下输出不可解析 | length 单独分类、不重试；限制总引用数、引用长度与动态 max_tokens |
| U02/U03 | 要求来源混淆、bool解释矛盾、漏用预注册搜索工具 | 通用指令契约；只验证指令提供，真实遵循改善 unknown |

原 UAT 整体1/6、Coding0/2、语义应用0/2和6452摘要Token保持原记录。安全拒绝不等于模型能力已被否定；也不能用合成通过改判历史失败。
