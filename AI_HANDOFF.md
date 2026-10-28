# AI_HANDOFF

## 当前目标与状态

Core Refactor R1，分支 codex/lean-core-refactor-v1，精确基线 1b5af3543dde6bde51c3863a6d88b3c40ab8d778（codex/repo-map-scoped-v2）。实现和离线回归完成，交付为本分支提交并 Push；最终 SHA 由交付消息给出，或 git log -1 --format=%H。不是新 Phase，不创建 Tag/ZIP。

## 实现与决定

- 唯一 AgentLoop 保留构造、handle_message、循环和请求调度；context_preparation、tool_dispatch、turn_lifecycle 三个函数模块承接上下文、工具批次/安全事件和任务持久化/清理。状态仍由 AgentLoop 持有，转发入口与 Evaluation 子类兼容；14 个提取函数 AST 与基线一致。
- AgentLoop 唯一组合宿主 before_fallback 和 CodingController 预算；删除 CLI/Web 的覆盖，宿主先检查，拒绝不发送备用请求。Provider Chain 顺序、任务内保持、新任务重置不变。
- 共享 config → ToolRegistry 参数映射；合并相同停止结果分支、重复结果类型检查与 session/context/skills 配置取值逻辑。MCP owning task、CLI/Web 审批与关闭边界分开保留；严格 Web launch 校验不强行合并。
- Patch/Receipt、命令审批/Seatbelt、Session/EventStore 格式、Streaming 终态、请求预算未放宽。历史 Benchmark/Fixture/Gold、冻结材料、账本和 C01/C02 未改；真实模型请求 0。

## 文件、计量和验证

生产：agent/loop.py、context_preparation.py、tool_dispatch.py、turn_lifecycle.py、app.py、web/runtime.py、tools/registry.py、config.py。详见 docs/core-refactor-r1.md（架构、差异、复测命令与局限）。运行方式未变，README 不改。

Python 文件 106→109，总物理行数 13989→14063（+74），loop 844→361；整体代码量没有下降，主要收益是职责与少量重复逻辑精简。同机同 Python/依赖无并发测试计量：模块导入基本持平，固定 Mock 单轮中位数 0.4671→0.4550ms，不宣称显著加速。

专项 436 项、Streaming 补充 92 项、新增 R1 5 项通过。全量发现两处基线已有问题，均在原 SHA 复现：Campaign 旧工具计数更新为完整 11 项名称/重复数量断言；smoke 测试使用完整合成 GatewayConfig，旧探针替换客户端同步 _clients 表。所有旧断言保留或加强；分别 33/13 项通过，未运行真实 smoke。剩余 32 组718项通过。最终完整 check_phase：60组1739项、零失败/跳过，354.28秒，退出码0（专项与全量有重叠）。Python compileall、两份 JS 语法和 diff --check 通过。

## 边界、下一步与不要重复

本轮完成；下一步仅按新需求推进，不自动进入新 Phase。未来可继续减少共享状态耦合，但不要为缩短文件删除安全门，也不要无授权运行模型评测。历史 scripts/Evaluation 不迁移。

工作位于独立 APFS 工作树；原 ExFAT 目录 main、app.py 中文注释及 workspace/instructions/USER.md 未提交偏好保留。共享 Git 有 AppleDouble pack index 警告，未改共享元数据；未提交凭证、真实配置、会话历史或临时计量文件。旧 Phase/Tag/ZIP、历史 UAT 结论保持原状。
