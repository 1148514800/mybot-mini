# AI Handoff

## 当前状态

Phase 07 Skills 已完成并独立归档；phase-07 指向功能提交 0baee7af9d74236a8846e242c14cf4e5efb3835b。ZIP：../mybot-mini-snapshots/phase-07.zip。Phase 01–06 保持不变，不进入 Phase 08。skills.enabled 默认 false，本地配置和模板已补齐。

## 实现与修改

- mybot/skills/registry.py、__init__.py：确定扫描、元数据专读、PyYAML SafeLoader/重复键检查；32 技能/64 KiB 文件/8 KiB frontmatter，严格元数据/路径/文本验证，拒绝符号链接。
- tools/skill.py：load_skill/read_skill_reference，复用 ToolRegistry/ToolResult，只读 SKILL.md 与 references 下 .md/.txt/.rst。
- agent/loop.py、context.py：初始化注册工具与元数据索引，原 ReAct 选择加载；读取不进入 Plan.observe，无活跃技能缓存。
- agent/context_manager.py：根据调用名/ID 完整保护技能读取结果，放不下就失败，旧整轮历史可摘录，不改 Session/JSON。
- config.py、模板、pyproject.toml、uv.lock：skills 开关/根路径，新增轻量 PyYAML 6.0.3 解析真实 YAML。
- scripts/check_skills.py、check_phase.py、旧回归与归档测试：16 技能测试；旧测试显式 skills=false；临时归档夹具同步源码/依赖/示例。
- skills/file-summary、code-review：两份可用说明与参考清单；docs/phases/phase-07.md、索引、README 完整教程。

## 验证

Skills 16 项通过：关闭、发现/元数据渐进读取、模型加载/参考/文件链、YAML和重复名称、路径/链接/文本/大小限制、脚本不执行、消息配对、Planning 不伪造证据、完整文本预算、恢复/clear。Phase 01/02 回归、Session12、Planning12、Persistence16、Context18 均通过；归档安全测试通过。已从干净工作树导出 ZIP，独立安装 uv sync --frozen、编译和全部回归通过；restore_phase.sh 07 独立还原后再次验证通过，ZIP 73 条目含两份技能与参考资料，不含真实配置/Session/用户未提交文件。真实模型手工测试未执行。

## 局限与决策

只支持可信本地技能；不执行 scripts、不下载远程、不授予 allowed-tools 权限。技能正文为普通 Tool Result，索引仅 name/description；不是系统规则。Context 关闭时仅文件大小限制，开启时完整正文预算失败不裁剪。恢复只还原消息，不执行旧技能/Plan；没有技能激活状态或正文缓存。元数据变更需重启；无恶意并发文件系统/硬链接/签名防护或语义效果保证。

## 环境与用户修改

macOS/zsh、Python3.12+、uv，运行 uv run python mybot/main.py。skills.path 项目根相对，默认 ./skills，开关修改重启。app.py 与 USER.md 用户修改不提交；真实 Session/配置不输出、不归档。ExFAT ._* 尽量 COPYFILE_DISABLE=1 减少，归档排除，独立验证使用 APFS。

## 下一步

Phase 07 已结束，后续由用户指定。不覆盖旧 Tag/ZIP，不重复实现 SkillRegistry，不进入 Phase 08；历史原理见 docs/phases。
