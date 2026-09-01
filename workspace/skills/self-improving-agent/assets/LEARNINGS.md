# Learnings

Template notes for promoting durable MyBot learnings.

**Categories**: correction | insight | knowledge_gap | best_practice
**Areas**: agent | tools | browser | memory | session | state | config | docs
**Statuses**: pending | in_progress | resolved | wont_fix | promoted | promoted_to_skill

## Promotion Targets

| Target | Use For |
|--------|---------|
| `workspace/instructions/USER.md` | user-specific preferences |
| `workspace/instructions/SOUL.md` | agent behavior rules |
| `workspace/instructions/TOOLS.md` | tool gotchas and tool usage rules |
| `workspace/instructions/AGENTS.md` | workflow and architecture rules |
| `workspace/memory/memory.json` | structured durable facts |

## Example

```markdown
## [LRN-YYYYMMDD-001] best_practice

**Logged**: 2026-04-23T10:00:00Z
**Priority**: high
**Status**: promoted
**Area**: tools

### Summary
Execution requests must not be considered complete without actual tool calls

### Details
The model repeatedly replied with “已打开...” even when no tool call happened.

### Suggested Action
Add loop-level protection for action requests and document the rule in SOUL.md or TOOLS.md.

### Promotion Target
- SOUL.md

---
```
