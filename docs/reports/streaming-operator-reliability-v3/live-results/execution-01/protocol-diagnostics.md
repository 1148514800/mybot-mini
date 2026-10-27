# Protocol / cancellation distinction

| Case | Chunks | finish/count | Natural EOF | SDK closed | Trusted terminal | Error code |
|---|---:|---|---|---|---|---|
| N01 | 113 | stop/1 | true | true | true | null |
| N02 | 1 | null/0 | false | true | false | stream_user_or_caller_cancelled |

N01 completed-stream protocol PASS requires all terminal/EOF/close/persistence checks; finish_reason alone is insufficient. N02 cancellation PASS deliberately lacks EOF and a trusted terminal. Its diagnostic phase sdk_iteration/chunk1 records user cancellation, not provider failure. No GeneratorExit inference or artificial fallback. At most8 safe structural chunk descriptions per stream are published; no raw content or original chunks.

Empty Registry and no tools observed; no incomplete call executed. This batch is not a malformed-call stress test. Existing parser/authority/failover code and registered stream/include_usage options were unchanged. SDK retries0; each physical reservation corresponds to one actual HTTP send and real provider response. N02 provider Usage absent, observed/settled values remain null. The actual SDK close is a local resource guarantee, not an acknowledgement of remote billing cancellation.

Timing JSON uses host monotonic timestamps and separates registered barriers. Browser same-clock first-visible-preview latency and exact Stop-to-close latency were not captured and remain null; host SSE emit time is not substituted for browser visibility. N02 has no text/SSE preview before Stop; role-only genuine delivery satisfies the preregistered premise.
