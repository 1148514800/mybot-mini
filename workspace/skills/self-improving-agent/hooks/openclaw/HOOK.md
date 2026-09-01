---
name: self-improving-agent
description: "Inject a reminder to capture durable learnings for the MyBot project."
metadata: {"openclaw":{"emoji":"🧠","events":["agent:bootstrap"]}}
---

# Self-Improvement Hook

Inject a short reminder during bootstrap:

- log unresolved failures into this skill’s `.learnings/`
- promote stable rules into `workspace/instructions/*.md`
- promote structured facts into `workspace/memory/memory.json`

This hook is optional and only useful if your environment supports OpenClaw-style bootstrap hooks.
