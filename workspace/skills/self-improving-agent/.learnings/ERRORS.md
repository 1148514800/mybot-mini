# Errors Log

Store unresolved or candidate failures discovered while working on this MyBot project.

Use this file for:

- tool failures worth remembering
- browser/session failures
- execution-flow bugs
- repeated mistakes in storage, memory, state, or session handling

Promote stable fixes into:

- `workspace/instructions/TOOLS.md`
- `workspace/instructions/SOUL.md`
- `workspace/instructions/AGENTS.md`

Template:

```markdown
## [ERR-YYYYMMDD-XXX] short_name

**Logged**: ISO-8601 timestamp
**Priority**: low | medium | high | critical
**Status**: pending
**Area**: agent | tools | browser | memory | session | state | config | docs

### Summary
One-line description of the failure

### Error
Actual error output or failure symptom

### Context
- What was being attempted
- Which file / tool / workflow was involved

### Suggested Fix
What should change next time

### Promotion Target
- TOOLS.md | SOUL.md | AGENTS.md | memory.json | none yet

---
```
 
## [ERR-20260816-001] xiaohongshu_publish_duplicate_on_retry 
 
**Logged**: 2026-08-16T20:44:00+08:00 
**Priority**: high 
**Status**: pending 
**Area**: tools | browser 
 
### Summary 
小红书发布笔记时，首次发布命令超时中断后盲目重试，导致同一内容重复发布 3 条。 
 
### Error 
发布命令执行超过 30 秒限制被中断，agent 未先检查是否已发布成功即重试，最终产生 3 条重复的「agent测试」笔记（20:35/20:36/20:37）。 
 
### Context 
- 正在执行：小红书创作服务平台发布图文笔记，内容「agent测试」 
- 涉及工具：browser_* 操作小红书发布表单、点击发布按钮 
- 工作流：上传图片 -> 填写标题/正文 -> 点击发布 -> 等待跳转确认 
 
### Suggested Fix 
发布类操作超时或被中断后，不得直接重试；先打开「笔记管理」页面检查最近发布记录，确认没有成功发布后再重试。 
 
### Promotion Target 
- TOOLS.md 
 
---
 
## [ERR-20260816-002] empty_reply_after_user_request 
 
**Logged**: 2026-08-16T20:44:10+08:00 
**Priority**: medium 
**Status**: pending 
**Area**: agent 
 
### Summary 
用户第一次要求「发布 agent 测试」时，模型结束处理但未返回任何文本结果。 
 
### Error 
用户请求执行发布任务，本轮处理以空回复结束，用户看不到任何进展或结果说明。 
 
### Context 
- 正在执行：用户要求在小红书发布内容 
- 属于执行类请求，却未给出任何中间或最终说明 
 
### Suggested Fix 
执行类任务每一步都应说明意图与结果；若处理被中断/超时，也要明确告知用户当前状态与下一步。 
 
### Promotion Target 
- SOUL.md | AGENTS.md 
 
---
