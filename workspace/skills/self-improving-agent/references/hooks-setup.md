# Hook Setup

This skill does not require hooks to be useful in MyBot.

The normal workflow is manual:

1. notice a repeated error, correction, or missing capability
2. log it to `.learnings/`
3. promote stable rules to:
   - `workspace/instructions/*.md`
   - `workspace/memory/memory.json`

If your environment supports external bootstrap hooks, you may use the files in `hooks/openclaw/`, but they are optional and not required by MyBot itself.
