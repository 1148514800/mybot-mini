---
name: self-improving-agent
description: Capture recurring mistakes, user corrections, missing capabilities, and durable project learnings for this MyBot codebase. Use when a tool or command fails, the user corrects prior behavior, a repeated weakness is discovered, or a fix should be promoted into workspace memory or instruction files.
---

# Self-Improving Agent

Record useful learnings for this MyBot project, then promote stable ones into the right long-term location.

This skill is for **durable improvement**, not for temporary task notes.

## Use This Skill When

- A command, tool call, or browser operation fails in a way worth remembering
- The user corrects a wrong assumption or wrong behavior
- The agent repeatedly makes the same mistake
- A missing capability or missing guardrail is discovered
- A workaround becomes a stable project rule
- A recurring project fact should be promoted into long-term memory or instruction files

## Do Not Use This Skill For

- One-off transient webpage state
- Temporary browser URLs that belong in runtime state
- Raw conversation history that already belongs in `workspace/sessions/`
- Current execution state that belongs in `workspace/state/runtime_state.json`

## Project-Specific Destinations

Choose the destination by information type.

### 1. `workspace/memory/memory.json`

Write here when the learning is a **structured long-term fact**:

- user preference
- stable project fact
- durable browser/session convention
- reusable key/value memory

Examples:

- default reply language
- default browser session for a domain
- config path
- stable repo convention

### 2. `workspace/instructions/USER.md`

Write here when the learning is a **user-specific preference** that should guide future interactions.

Examples:

- preferred answer style
- preferred language
- file-editing preferences
- collaboration preferences

### 3. `workspace/instructions/SOUL.md`

Write here when the learning is a **behavior rule** for the agent.

Examples:

- how to behave before editing files
- how to distinguish memory vs instructions
- how to respond to execution requests

### 4. `workspace/instructions/TOOLS.md`

Write here when the learning is a **tool usage rule or tool gotcha**.

Examples:

- `browser_attach` vs `browser_open` vs `browser_goto` vs `browser_tab`
- `playwright-cli` limitations
- session liveness caveats
- `exec` tool restrictions

### 5. `workspace/instructions/AGENTS.md`

Write here when the learning is a **workflow or agent-architecture rule**.

Examples:

- when to summarize sessions
- how to separate session/state/memory
- delegation or review workflow rules

### 6. `.learnings/*.md` inside this skill

Use this skill’s local `.learnings/` files as the **raw intake area** for:

- unresolved failures
- feature requests
- candidate improvements that are not yet stable enough to promote

Promotion targets are the project files above.

## Recommended Workflow

### A. When something fails

1. Decide whether the issue is:
   - transient
   - project-specific and recurring
   - stable enough to promote
2. If it is only raw intake, append it to:
   - `.learnings/ERRORS.md`
   - `.learnings/LEARNINGS.md`
   - `.learnings/FEATURE_REQUESTS.md`
3. If the lesson is already stable, update the real project destination directly.

### B. When the user corrects the agent

1. Extract the corrected rule
2. Decide destination:
   - user preference -> `USER.md` or `memory.json`
   - behavior rule -> `SOUL.md`
   - tool rule -> `TOOLS.md`
   - project fact -> `memory.json`
3. If the correction is still ambiguous, log it to `.learnings/LEARNINGS.md` first

### C. When a repeated weakness is discovered

Examples in this repo:

- execution requests answered without tool calls
- browser session exists in state but is not really alive
- session history too large and wastes tokens
- wrong destination chosen between `memory` and `SOUL.md`

For these, prefer promoting the rule into the real project files instead of only logging it.

## Logging Rules

Use the local `.learnings/` directory for unresolved or candidate learnings:

- `.learnings/ERRORS.md`
- `.learnings/LEARNINGS.md`
- `.learnings/FEATURE_REQUESTS.md`

Keep entries short and actionable.

Each entry should say:

- what happened
- why it matters
- what should change
- where it should eventually be promoted

## Promotion Rules For This Project

Promote a learning when one of these is true:

- it has already happened more than once
- it changes future agent behavior
- it affects multiple files or workflows
- it is a stable user preference
- it is a durable project fact

### Prefer promotion over endless logging

If the lesson is already clear and stable, do **not** stop at `.learnings/`.
Update the real destination file.

## Examples

### Example 1: user says “以后每次修改前先给我看具体改动”

Destination:

- `workspace/instructions/USER.md`

Reason:

- this is a user collaboration preference

### Example 2: browser tool often claims success without calling tools

Destination:

- `.learnings/ERRORS.md` first if still unresolved
- then `workspace/instructions/SOUL.md` or `TOOLS.md` once the guardrail is clear

Reason:

- this is a behavior/tooling rule, not memory

### Example 3: `github.com` should default to `github_main`

Destination:

- `workspace/memory/memory.json`
- or `config/config.json` if it is a static browser config rule

Reason:

- this is a durable structured fact

### Example 4: session summaries should be used instead of full history

Destination:

- `workspace/instructions/AGENTS.md`
- optionally `.learnings/LEARNINGS.md` while evolving the approach

Reason:

- this is an agent architecture/workflow rule

## Important Distinctions

### Memory vs State

- `memory.json` = durable fact
- `runtime_state.json` = current state

Do not write transient browser state into memory.

### Memory vs Instructions

- `memory` = structured fact or preference
- `instructions/*.md` = behavioral or workflow rules

### Learnings vs Final Destination

- `.learnings/*.md` = intake queue
- `memory.json` / `USER.md` / `SOUL.md` / `TOOLS.md` / `AGENTS.md` = durable destination

## What Good Output Looks Like

A good use of this skill results in one of these:

- a concise learning entry in `.learnings/`
- a promoted durable rule in `workspace/instructions/*.md`
- a promoted structured fact in `workspace/memory/memory.json`

It should not produce long essays, duplicated documentation, or raw transcript dumps.
