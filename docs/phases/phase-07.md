# Phase 07：Agent Skills 系统

archive-ready: true

## 1. 学习目标与 Agent Skills

技能是用于指导模型完成特定任务的本地操作说明包，入口 SKILL.md 包含 YAML 元数据与 Markdown 说明。学习目标是发现技能、按需提供内容、复用既有工具并控制权限和上下文，而不是建立第二个 Agent 循环。

本项目参考 [Agent Skills 开放规范](https://agentskills.io/specification)。name 和 description 是必须字段；技能名称与父目录一致，描述说明用途和触发场景。这里实现本地可信目录和文本资源子集，不支持远程安装或脚本执行。

## 2. Skill 与 Tool 的区别

Skill 告诉模型“如何完成任务”；Tool 是 Python 实际执行的能力。读取总结说明不会读取或写入用户文件，读取审查说明也不会运行代码或测试。模型获得技能后，仍通过 list_files/read_file/write_file 操作工作区。

load_skill 与 read_skill_reference 本身也是普通 Tool，只返回说明文本。不提高指令优先级、不授予 Shell 权限、不自动执行技能步骤。实际行为由原有 ToolRegistry、Planning 和工作区路径约束控制。

## 3. SKILL.md 结构与示例目录

```text
skills/
  file-summary/
    SKILL.md
    references/checklist.md
  code-review/
    SKILL.md
    references/checklist.md
```

```yaml
---
name: file-summary
description: 读取并总结工作区文件，在摘要、要点提取或保存总结时使用。
---
# 文件总结
先定位路径，用 read_file 读取，再依据实际内容整理。
按需读取 references/checklist.md。需要保存时用 write_file。
```

name 为 1–64 字符的小写字母/数字/连字符名称（支持 Unicode 字母数字），不得首尾连字符或连续连字符，必须与目录名一致。description 为 1–1024 字符的非空字符串。可选 license、compatibility、metadata、allowed-tools 会校验类型，compatibility 最多 500 字符，metadata 只允许字符串到字符串的映射。

allowed-tools 只作为元数据接受，本阶段不赋予额外能力、不实现其权限声明。未知字段、重复 YAML 键、Python 对象标签和坏 YAML 会拒绝。YAML 隐式类型也会检查：如 metadata.version 需要字符串时应写成带引号的值。

## 4. Progressive Disclosure 的三个层次

1. 启动读取 name/description，提供简洁目录。没有将所有正文放进每次请求。
2. 模型认为技能适用时，通过 Function Calling 调用 load_skill(name)，返回完整 SKILL.md。
3. 需要参考材料时调用 read_skill_reference(name, path)，读取 references 下允许的文本。

没有关键词路由器或独立分类模型。无关问候可直接回复；是否选择技能取决于模型，模拟测试不保证线上模型一定会选对技能。

## 5. SkillRegistry 发现、验证与按需读取

SkillRegistry 构造时对配置目录排序扫描。隐藏项（含 ExFAT 的 ._*）忽略，普通非目录文件忽略；技能目录缺少 SKILL.md 则明确报错。最多 32 个技能，每个入口/参考文件最多 65536 字节，frontmatter 最多 8192 字节。

发现阶段只用二进制 readline 消费起始和结束 frontmatter 分隔行，遇到结束行立即停止。正文不解码、不加载、不缓存；stat 的大小检查不读取正文。分隔行用于识别 Markdown 的 YAML 边界，元数据实际交给 PyYAML SafeLoader 解析，支持折叠字符串、引号和嵌套映射，绝非用字符串切割模拟 YAML。

自定义 MetadataLoader 拒绝重复键。PyYAML 是本阶段唯一新增轻量依赖，避免手写不完整 YAML 语法；uv.lock 锁定 pyyaml 6.0.3。

index 返回仅 name/description 的确定顺序列表。read(name) 读取完整 SKILL.md；read(name, path) 按指定技能读取参考资料。加载前重新验证元数据与启动索引相同；名称/描述等改变则要求重启，正文可以按需重新读取。读取还会检查 UTF-8、NUL、实际读取大小，损坏文件明确返回错误。

## 6. AgentLoop、Function Calling 与核心调用链

```text
GatewayConfig.skills_enabled
  → AgentLoop 初始化 SkillRegistry
  → ToolRegistry 注册 load_skill/read_skill_reference
  → ContextBuilder 获得 name/description 目录
用户输入 → 原 ReAct 模型请求（含索引与工具 Schema）
  → assistant.tool_calls(load_skill)
  → AgentLoop._execute → ToolRegistry.execute → SkillTool.execute
  → SkillRegistry.read → ToolResult → role=tool + tool_call_id
  → 模型按需 read_skill_reference 或调用实际文件工具
  → 原 Session 完整轮次提交与 SessionStore 保存
```

ContextBuilder 在 System 中提供带数据标签的目录信息和应用级使用规则；只放元数据，不放技能正文。技能实际内容作为普通工具结果传递，不能覆盖系统规则、用户要求或文件权限。

两个读取工具复用同一个精简 SkillTool 类与现有 Tool 接口。其参数严格检查，load_skill 只接受 name，read_skill_reference 必须接受 name 和 references/... 路径，不接受任意额外字段。不增加额外执行循环，也不自动选择技能或执行步骤。

## 7. 路径、安全边界与权限

skills.path 相对项目根解析，不随 cwd 改变。开启时要求目录存在并验证入口。技能根、技能目录、SKILL.md 和参考文件路径内的符号链接均拒绝（即使指向目录内部也保守拒绝）。参考路径禁止绝对路径、反斜线、.. 越界和非规范路径。

参考工具只允许 references/ 下 UTF-8 的 .md/.txt/.rst 文档。scripts/、assets/、Python、Shell、二进制文件不通过该接口加载或执行。根目录是用户指定的可信本地来源，不自动下载或安装。

文件工具权限不变：load_skill 的受限读取能力仅针对该技能目录，不是通用外部文件读取接口。Skill 文本不能让 read_file/write_file 访问 workspace 外。引用外部路径或符号链接不会扩大权限。

可信根仍要求用户管理内容；不要放入私有凭证。没有恶意本地进程竞态、硬链接、签名验证或远程供应链保护的完整防御。路径检查不应被理解为允许加载不可信任意目录。

## 8. ContextManager、Planning、Session 的兼容性

技能索引属于完整 System 数据，因此与消息结构及两个工具 Schema 一起进入字符计量。开启 Context 后，clip 从 assistant.tool_calls 建立技能读取的 ID 集合，跳过这些 Tool Result 的正文裁剪，包含 SKILL.md 与参考资料。若本轮完整技能和受保护协议放不进预算，明确抛 ContextBudgetError，不发送下一请求，不静默剪掉关键操作说明。

旧技能历史可按完整轮次替换为标明来源的普通 assistant 摘录，但绝不会升级成 System 指令。保留的技能 Tool Result 仍完整；只有普通文件工具正文沿用裁剪策略。Context 关闭时不执行总字符预算，技能文件大小限制仍始终有效。

AgentLoop 将技能读取视为信息加载，类似规划控制工具：不调用 Plan.observe，成功加载本身不积累执行证据。实际文件操作仍需要合法活动步骤，依据真实 ToolResult 更新 verified/failed；不因读取技能而把 pending/in_progress 直接变成 completed。

Session/SessionStore 继续保存完整原始请求与结果，JSON v1 不变。恢复历史不执行任何旧工具或恢复 Plan。没有“已激活技能”全局状态或正文缓存；/clear 清空原有历史和计划后，新任务仅有元数据目录，不带旧正文。索引属于目录发现，保留索引不等于继续执行旧技能。

## 9. 配置与 macOS + uv 使用

```json
{
  "skills": {"enabled": false, "path": "./skills"}
}
```

默认关闭。enabled 必须为 JSON 布尔，path 必须非空路径字符串；配置错误明确报错。启用后重启扫描目录；目录或元数据修改后重启刷新。仅修改正文可在下一次 load_skill 读取。

```bash
bash scripts/restore_phase.sh 7
cd ../mybot-mini-learning/phase-07
uv sync --frozen
cp config/config.example.json config/config.json
# 配置本地 Key，skills.enabled=true；需要预算时 context.enabled=true
uv run python mybot/main.py
```

手工任务示例：“请调用 file-summary 技能读取并总结 instructions/SOUL.md”；“请使用 code-review 静态审查工作区中的 Python 文件”。输入 /clear 清空会话。真实模型手工验证尚未执行，是否自动选 Skill 仍需要线上观察。

```bash
uv run python -m scripts.check_skills
uv run python -m scripts.check_phase
uv run python -m scripts.test_phase_archives
uv run python -m compileall -q mybot
```

ExFAT 开发目录可用 `-x '/\._'` 排除 AppleDouble；实际独立归档在 APFS 临时目录编译。示例技能和参考文档均包含在源码 ZIP，不含运行时 Session 或真实配置。

## 10. 自动化测试、变化及局限

16 项 Skills unittest 使用临时目录与模拟 LLM，均通过：关闭兼容、确定发现与正文不预读、目录索引和无关任务、模型 load/ref/真实文件工具链、YAML/字段/重复键/对象标签错误、重名与目录名不符、符号链接与路径穿越、参考白名单/缺失/元数据变化、脚本不执行、加载不构成规划证据、完整文本不裁剪、超预算不发送、索引/Schema 计量、持久化恢复不重放与 clear、数量/大小/文本限制、配置路径与类型。

Phase 01/02 工具回归、Session 12 项、Planning 12 项、Persistence 16 项、Context 18 项通过。旧测试明确 skills=false，避免用户配置影响旧行为。归档安全测试通过，独立快照冻结安装、编译与统一回归通过；模拟结果不等于真实 LLM 技能选择验证。

Phase 06 只有通用工具和请求预算；Phase 07 新增技能目录与两个只读加载工具，保留一个 ReAct 循环和所有既有模块。只支持本地可信文本，32 个技能、64 KiB 文件上限；无热更新目录发现、远程安装、自动脚本执行、allowed-tools 权限扩展、MCP、多 Agent、完整技能标准运行时或语义任务验证。Skill 指导不能保证模型正确执行或保证审查/总结质量。

旧 Phase 01–06 Tag/ZIP 不变，app.py 和 USER.md 用户修改保留，不进入 Phase 08。
