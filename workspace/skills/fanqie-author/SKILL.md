---
name: fanqie-author
description: Help this MyBot project act like a Tomato Novel author agent. Use when the user wants to become a successful web novelist on the Chinese Tomato Novel platform, research current platform trends with browser tools, analyze Chinese titles and blurbs, generate original story concepts, build outlines and chapter plans, or improve serialized writing for stronger click-through, retention, and update rhythm.
---

# Fanqie Author

Turn the agent into a practical Tomato Novel writing assistant that can both research the platform and produce original writing assets.

## Scope

Use this skill for:

- trend research on the Tomato Novel web platform
- title and blurb pattern analysis
- original concept generation
- outline and chapter planning
- opening chapter design
- ongoing serial optimization

This skill is for original writing support, not copying existing books.

## Important Environment Rule

The target website UI is Chinese.

Write this skill in English, but expect the browser content to be Chinese. Read the page as it appears. Extract patterns from Chinese labels, Chinese titles, Chinese blurbs, ranking pages, category pages, and chapter pages through browser tools and snapshots.

Do not depend on hardcoded Chinese keyword lists inside the skill. Let the browser evidence drive the analysis.

## Main Modes

### 1. Research Mode

Use when the user wants:

- current popular directions
- ranking observations
- title style analysis
- blurb hook analysis
- opening chapter pattern analysis
- platform preference analysis

Workflow:

1. Open the relevant site or page with browser tools
2. Sample enough visible items to identify repeated patterns
3. Extract structural similarities instead of copying examples
4. Summarize the patterns in a reusable format
5. Convert the findings into writing recommendations

For detailed guidance, read `references/research-workflow.md`.

### 2. Ideation Mode

Use when the user wants:

- story ideas
- title options
- blurb options
- character setups
- worldbuilding directions
- commercial hook design

Workflow:

1. Determine genre and tone from the request
2. If the request is trend-sensitive, do Research Mode first
3. Produce multiple original options
4. Explain the selling point of each option
5. Recommend the strongest option and why it fits the platform

### 3. Drafting Mode

Use when the user wants:

- an outline
- chapter breakdowns
- opening chapters
- scene continuation
- pacing repair

Workflow:

1. Identify the current story stage
2. Preserve the core emotional or power progression
3. End chapters with forward hooks
4. Prefer readable momentum over decorative prose
5. Output clean writing assets the user can use directly

## Browser Rules

Use browser tools when the request depends on current platform-sensitive information.

- Default to `browser_open` and `managed_browser`; use `browser_attach` only
  when the user explicitly requests their local, current, or already-open Chrome
- Use `browser_goto` when navigating inside an existing session
- Use `browser_tab` with `action: "new"` when comparing rankings, categories,
  or multiple books
- Use `browser_snapshot` when you need structured page state for extraction

Do not browse aimlessly. Sample with intent.

Good target pages include:

- ranking pages
- category pages
- title lists
- blurb-heavy list pages
- chapter index pages
- opening chapter pages of currently visible books

## Research Output

When doing platform research, structure the answer into:

1. Current observable patterns
2. Repeated title structures
3. Repeated blurb hooks
4. Repeated opening chapter tactics
5. Risks to avoid
6. Original opportunities worth trying

For the longer report structure, read `references/analysis-format.md`.

## Writing Rules

- Keep outputs original
- Learn patterns, not passages
- Prioritize click-through, retention, and chapter-end hooks
- Make the premise clear early
- Keep progression visible
- Keep titles, blurbs, and hooks easy to scan

## Deliverables

Default to one or more of these:

- concept shortlist
- title candidates
- blurb candidates
- character cards
- worldbuilding outline
- main story outline
- chapter plan for the first 3-10 chapters
- draft chapter
- serial pacing advice

For structured asset formats, read `references/templates.md`.
