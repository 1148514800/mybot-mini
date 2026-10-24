# 旧写入能力迁移

新安装默认不提供 write_file。旧配置缺省行为也收敛为只读，这是有意的安全迁移；不能在历史测试的压力下恢复隐式写入。

需要旧工具名称的交互程序可显式配置：

```json
{"coding":{"enabled":false,"patch_mode":"off","file_access":"legacy_confirm"}}
```

CLI 和 Web 通过独立 FileApprovalRequest 逐次展示完整目标相对路径和替换内容，批准本次后才提交内部 Receipt。不缓存授权、不从聊天 yes 推断授权；无法安全完整展示（敏感值、超过 10KB JSON、Web 二次格式化超过原审批上限）则拒绝。空文件覆盖当前拒绝（原生协议也没有空锚点插入，需要明确宿主操作或另行扩展）；不再自动创建父目录。相对路径、敏感路径、符号链接和文件元数据限制可能比旧 Phase 严格。没有 OS 沙箱；不建议作为日常 Coding 方式。

教学 Phase 文档与历史 Tag/ZIP 保持原样。其历史说明在当时版本成立；运行旧示例要么还原对应历史快照，要么按本迁移显式选择兼容策略。README 的当前说明优先，不能继续宣传新默认支持写入。

测试迁移逐项见 compatibility-report.md。scripts/legacy_write_fixture.py 仅是显式传入生产 legacy_confirm 和合成逐次审批的测试调用方，没有生产环境变量后门；相同生产工具仍执行原来的 Patch 前置检查。旧评测 runner 明确选择兼容工作流，离线用合成批准，Live 必须真实 CLI 逐次批准。Tool Agent Harness 只转发显式配置和宿主 Provider，默认仍只读。其旧 builtin-write 用例显式提供配置及合成批准，冻结任务本身、期望产物和 Judge 不变。
