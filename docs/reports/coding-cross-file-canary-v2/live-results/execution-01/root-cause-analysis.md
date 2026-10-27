# Observed evidence and bounded diagnosis

Observed: request4 ledger elapsed 44.967980s. First SDK chunk arrived 43.555308s after admission;228 chunks were observed, with no text/finish/terminal/EOF. Native consumer diagnostic is stream_user_or_caller_cancelled at sdk_iteration/chunk228, origin caller_cancellation. SQLite model.failed retains only request_failed; Controller's persisted Web view retains blocked/invalid without the internal stop reason. No raw chunks or hidden reasoning text were retained.

Frozen code: config request timeout90s; ProviderFailoverClient.create wraps the primary dispatch/whole native stream consumption in asyncio.timeout(request_timeout_seconds/2), i.e.45s. After any chunk it suppresses fallback on timeout. AgentLoop catches TimeoutError/APITimeoutError and stops blocked/model_request_timeout. The browser operator issued no Stop and did not hit its1150s deadline; native task900s/Web1200s windows had not elapsed.

Strong inference: primary local45s deadline cancelled request4 just after first-chunk latency consumed most of that window. This is supported by timing and frozen control flow, but the precise deadline origin was not explicitly exported in the persistent evidence. Keep that qualification; do not rewrite the recorded error to stream_local_timeout, assert supplier fault, infer slow reasoning contents, token exhaustion, or a model coding defect. Incomplete output never became a tool call or Patch.

Observed failure scope: real cross-file coding never reached Preview/Receipt/command. The known Bug modules remain. Unused request budget is irrelevant to the consumed one-Attempt rule. No recovery, longer timeout, fallback override, refreeze or retry is permitted for this batch.

Next separate engineering question: does reserving half of90s for fallback over the entire streamed primary response create insufficient useful-stream time after a long TTFT? Future offline diagnosis should record deadline owner/budget elapsed at cancellation, separate first-chunk and completion bounds, and test late-first-chunk streams. Any production or canary change must be a new task with its own tests/freeze; no fix was applied here.
