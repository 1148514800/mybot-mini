# Real SDK streaming integrity

| Request | Model | Chunks | finish_reason / count | EOF | SDK closed | Trusted | Usage in/out/total |
|---:|---|---:|---|---|---|---|---|
| 1 | deepseek-v4.1-flash | 23 | tool_calls / 1 | yes | yes | yes | 808/46/854 |
| 2 | deepseek-v4.1-flash | 24 | tool_calls / 1 | yes | yes | yes | 964/48/1012 |
| 3 | deepseek-v4.1-flash | 85 | stop / 1 | yes | yes | yes | 1062/83/1145 |

All fixed protocol error codes null. Natural EOF and actual SDK close are independently observed; no inference from finish_reason alone. At most 8 final structural chunk summaries per stream are retained. Empty legacy function_call metadata appears and is accepted under the existing parser; no nonempty legacy call was executed. The real initial list_files and later README read_file calls were assembled by the unchanged parser. Only the latter executed, after native authority checks. Paired tool results remain in later SDK requests with executed=false for the skipped call.

No malformed/incomplete call was observed; existing rejection rules were not altered, but this sample cannot claim an adversarial malformed-call Live test. No fallback, retry, synthetic chunk/tool injection or switch to non-streaming. The fixed first-stream operation barrier actually waited about 8 seconds; timing JSON separates it from provider latency. First browser-visible preview latency in a shared browser clock was not captured, so it remains null rather than substituted with host SSE emit time.

Final persisted response hash equals the final SDK assembled response hash. Protocol success and trusted persistence do not establish task semantic success. T03 cancellation and partial-reply trust remain untested in this batch.
