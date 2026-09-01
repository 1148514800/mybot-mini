# Examples

Concrete MyBot-oriented examples of when to use this skill.

## Example 1: wrong destination chosen

Situation:

- a stable user preference was about to be written into `SOUL.md`

Correct handling:

- user preference -> `workspace/instructions/USER.md`
- only use `SOUL.md` for agent behavior rules

## Example 2: browser session state is stale

Situation:

- `runtime_state.json` says a browser session exists
- `playwright-cli` says the session is not open

Correct handling:

- log the failure to `.learnings/ERRORS.md`
- if it becomes recurrent, promote a rule into `TOOLS.md`

## Example 3: model claims execution without tools

Situation:

- user says “打开 github”
- model replies “已打开 GitHub” without any tool call

Correct handling:

- log as a recurring agent/tooling weakness
- promote stable prevention rule to `SOUL.md` or `AGENTS.md`

## Example 4: durable project fact discovered

Situation:

- a domain should always map to a session

Correct handling:

- if static config -> `config/config.json`
- if durable learned fact -> `workspace/memory/memory.json`
