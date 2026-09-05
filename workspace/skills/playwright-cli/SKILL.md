---
name: playwright-cli
description: Control websites through this MyBot project's browser_* tools backed by Playwright CLI. Use when the user asks to open or navigate a website, inspect page content, click or fill elements, press keys, work with tabs, evaluate page JavaScript, or close a browser session. Also use for browser-based research that needs current page evidence.
---

# Browser Automation

Use the project's structured `browser_*` tools. Do not run `playwright-cli`
through `exec` when an equivalent browser tool exists.

## Workflow

1. Choose one browser mode and keep its session for the whole workflow:
   - Default: `browser_open` starts a visible Chrome as `managed_browser` with
     MyBot's persistent profile.
   - Only when the user explicitly asks for their local, current, or
     already-open browser: `browser_attach` connects to that Chrome as
     `local_browser`, preserving its profile, tabs, and login state.
2. Never switch modes as an automatic fallback. Report an attach/open failure
   for the requested mode. The first managed launch may require manual login;
   later launches reuse that login state.
3. Use `browser_goto` to replace the current page in the active session.
4. Use `browser_tab` with `action: "new"` when the current page must remain
   open. If a form or click opens a new tab, call it with `action: "list"`
   and then `action: "select"`; do not navigate the old tab to the same URL.
5. Read the page state returned by navigation and interaction commands. Call
   `browser_snapshot` when a fresh element map is needed. Use `browser_inspect`
   for structured selector, text, role, or placeholder queries. On large result
   pages, lower snapshot `depth` or narrow the query.
6. When the user asks for the Nth search result, call `browser_links` on the
   result container with a suitable URL filter. Select its 1-based `position`;
   do not infer order from ref numbers or count duplicate thumbnail/title links.
7. Interact with element refs from the latest snapshot when possible.
8. If the destination URL is known, use `browser_goto` directly instead of
   clicking the same result and then navigating to it.
9. After a final click, fill, Enter/Space, submit, send, or publish action,
   call `browser_verify` once with a concrete structured postcondition. Action
   success alone is not task success. When verification satisfies the request,
   stop calling tools and respond.
10. Use `browser_close` when the requested workflow is finished and the session
   is not meant to stay open.

## Tool Selection

- `browser_attach`: connect to the user's existing local Chrome through CDP
- `browser_open`: launch MyBot's separate Chrome with a persistent login profile
- `browser_goto`: navigate the current tab to a URL
- `browser_tab`: list, create, select, or close tabs
- `browser_snapshot`: inspect the page or one element
- `browser_inspect`: read DOM elements by selector/text/role/placeholder without caller JavaScript
- `browser_verify`: prove a postcondition by selector/text/role/placeholder/URL before reporting task success
- `browser_links`: list rendered, deduplicated links in visual order
- `browser_click`: click or double-click an element
- `browser_type`: type into the focused element or fill a target element
- `browser_press`: press a keyboard key
- `browser_eval`: evaluate JavaScript only when snapshot/inspect/links are insufficient; confirmation is required
- `browser_close`: close a session

## Sessions

Reuse either `local_browser` or `managed_browser` for all consecutive actions.
If a session is closed, restore it using the same mode that the user selected.
Do not silently switch between the user's Chrome and MyBot's managed profile.

## Interaction Rules

- Prefer snapshot refs over brittle CSS selectors. Pass `e102`, never `ref=e102`,
  when the snapshot displays `[ref=e102]`.
- Prefer `browser_inspect` over `browser_eval` for text, input, button, role,
  placeholder, and attribute lookup.
- Prefer `browser_links` for ordinal results such as "the fifth video".
- Take a new snapshot after navigation or when refs become stale.
- Follow `error_type` and `recoverable` metadata. For stale/not-found targets,
  use the Runtime refresh and relocate once; for ambiguity, narrow with inspect
  or ask the user; never repeat an identical `tool_syntax_error` action.
- Use `browser_eval` only for inspection or interactions not supported by the
  structured tools.
- Respect the structured browser result status. A `[browser error ...]` result is
  a failed action even when playwright-cli itself exited with code 0; page
  console error messages inside an otherwise successful result are only data.
- Do not claim that a page changed unless the returned state verifies it.
- A successful click/type/press is only action evidence. If `browser_verify`
  does not return `postcondition_met=true`, report the browser task incomplete.
- Respect the task budget: one browser initialization, one failed-action retry,
  bounded eval fallback, and bounded recovery. Do not explore indefinitely.
- Do not repeat navigation, click, playback, or verification after the requested
  final state has already been confirmed.
