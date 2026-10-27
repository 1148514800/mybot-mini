# Streaming Tool Call & Steer v2 — Live execution 01

LIVE PARTIAL / overall acceptance FAIL; remaining cases BLOCKED. Authorization: GRANTED_6_REQUESTS. Original offline preparation remains PASS; original reports are unchanged.

Input HEAD `41fcea237ed1c5be522c44d1cbc373e04acee8ea`; preregistration/frozen source `6337a20ae926f28cae0446f5e008bc754d2e14e0`. Same branch `codex/streaming-steer-real-uat-v2`, same uniquely prepared/frozen batch `streaming-steer-real-v2-20261026`. No prepare/freeze, code/model/parameter/message changes or reruns.

| Case | Task / semantic | Workflow / safety | Requests | Outcome |
|---|---|---|---:|---|
| T01 | FAIL: whole answer exceeds two sentences | Runtime workflow PASS; protocol/source/authority PASS | 3/4 | Steer reached two actual later requests; README read; final response saved |
| T02 | BLOCKED, not evaluated | Startup FAIL (exit 1); no Attempt, request or message | 0/1 | Plain port bind returned EADDRINUSE before make_app |
| T03 | BLOCKED, not executed | Not evaluated | 0/1 | Operator stopped after T02 startup failure |

T01 queued → native admission → persisted reservation → actual HTTP → provider response are independently observed. Old list_files was explicitly skipped with executed=false and a paired result. The next model chose read_file for the registered README, obtained the public identifier from that real result, read no examples and described the local Markdown-search purpose. The complete reply also included a status sentence and a colon-ended preamble before its two purpose sentences: three complete sentences overall. The frozen two-sentence requirement is FAIL; neither persistence nor the observer's heuristic count of 2 overrides this independent review.

Three real requests and three HTTP sends out of six. DeepSeek 3, GLM 0, retries/fallback/summary/Judge 0. Provider input/output/total = 2,834 / 177 / 3,011 tokens, complete and matched to the persistent ledger; cost=null (deployment price unavailable). All three streams have legal single terminal, natural EOF, SDK close and trusted persistence. Chunk counts 23 / 24 / 85. This demonstrates actual tool-call streaming on this sample, not long-term compatibility.

T01's own service exited 0 with port/lease release and consistent SQLite. T02 startup exited 1 despite prior connect/listener checks reporting free; no case ledger entry was created. Exact cause of EADDRINUSE is unproven. A transient socket state is plausible, but neither an unknown service nor TIME_WAIT is asserted as fact. No restart, port substitution, socket-policy change or later case was attempted.

The frozen browser exception path also raised an event-loop-closed error while closing an already-stopped Playwright context, preventing its profile-directory cleanup. All own Chrome processes were independently confirmed gone; only the known fresh owned profile was subsequently removed. Overall automated clean shutdown FAIL, eventual owned-resource cleanup verified. No execution_uncertain, reserved request, file mutation or authority violation found; no durable safety HALT was fabricated or cleared.

Fresh headed Chrome 152.0.7977.83, new 0700 profile, sandbox enabled. Bidirectional dual-profile Cookie/LocalStorage isolation passed. Original Chrome, old launcher/8765 and old private UAT assets were untouched. Final verify PASS (302 frozen source hashes), original configuration/workspace bytes and inodes / both DB identities intact, frozen metadata hashes unchanged. Only T01 has one completed Attempt; completed is a settlement state, not Task PASS. Remaining allowance was not reused.

Evidence: [case results](case-results.md), [protocol](streaming-integrity.md), [Steer/source](request-admission-vs-dispatch.md), [usage](resource-usage.json), [shutdown](shutdown-evidence.json), [security](security-audit.md). SDK/HTTP evidence contains hashes and bounded structural metadata only; no full prompts, raw chunks, replies, arguments, credentials or databases are published.
