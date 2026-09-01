/**
 * Optional bootstrap reminder for environments that support OpenClaw-style hooks.
 * Adapted for the MyBot project structure.
 */

import type { HookHandler } from "openclaw/hooks";

const REMINDER_CONTENT = `## Self-Improvement Reminder

When a durable lesson appears in MyBot:

- unresolved failure -> log to \`.learnings/ERRORS.md\`
- user correction or durable lesson -> log to \`.learnings/LEARNINGS.md\`
- missing capability -> log to \`.learnings/FEATURE_REQUESTS.md\`

Promote stable learnings to:

- \`workspace/instructions/USER.md\`
- \`workspace/instructions/SOUL.md\`
- \`workspace/instructions/TOOLS.md\`
- \`workspace/instructions/AGENTS.md\`
- \`workspace/memory/memory.json\``;

const handler: HookHandler = async (event) => {
  if (!event || typeof event !== "object") return;
  if (event.type !== "agent" || event.action !== "bootstrap") return;
  if (!event.context || typeof event.context !== "object") return;

  if (Array.isArray(event.context.bootstrapFiles)) {
    event.context.bootstrapFiles.push({
      path: "SELF_IMPROVEMENT_REMINDER.md",
      content: REMINDER_CONTENT,
      virtual: true,
    });
  }
};

export default handler;
