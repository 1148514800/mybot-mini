# Independent case results

| Dimension | T01 | T02 | T03 |
|---|---|---|---|
| Scenario premise | MET | BLOCKED before service start | BLOCKED |
| Task Success | FAIL (two-sentence format) | NOT EVALUATED | NOT EVALUATED |
| Workflow Success | PASS for completed native tool/Steer path | FAIL startup, no runtime | NOT EVALUATED |
| Safety / Integrity | PASS | No side effects or request; startup failure | No execution |
| UX | PARTIAL: correct admission warning, excessive response format | FAIL: service unavailable | NOT EVALUATED |
| Source / Turn integrity | PASS | NOT EVALUATED | NOT EVALUATED |
| Model Request Inclusion | PASS, requests 2 and 3 | NOT EVALUATED | NOT EVALUATED |
| Semantic Adherence | FAIL overall; action/content requirements pass | NOT EVALUATED | NOT EVALUATED |
| Stream protocol | PASS, 3 streams | NOT EVALUATED | NOT EVALUATED |
| Clean Shutdown | PASS, own process exit 0 | FAIL startup exit 1 | NOT EVALUATED |

T01's original in-flight request stayed byte-identical. Steer was queued after the first genuine nonterminal SDK chunk reached the consumer and before tools executed. The initial list_files model call was assembled but not executed; its result explicitly says executed=false, and the ID/hash pair is preserved. No actual list_files execution is claimed. The next real response called read_file for README; the result contains the public marker, which was absent from requests 1 and 2. Request 3 contains that actual result and returns the persisted final response. No example-file read or workspace write occurred.

The full final response is reviewed transiently from this new batch's own SQLite, with only verdicts/hash/count exported. It accurately distinguishes the skipped listing from the successful README read. Its two purpose sentences are preceded by an additional complete status sentence: the full-answer two-sentence contract fails. This is not repaired or narrowed after seeing the output. The UAT's regex feature undercounts adjacent Chinese sentences; it is preserved verbatim as evidence and explicitly not used as a grading oracle.

T02 server launch was attempted once but failed at the pre-app plain socket bind. There is no T02 Session/Attempt/message/model send. T03 was not launched. Their behaviors (not_applied, refresh, active-stream Stop/Usage/close) remain unverified by this Live batch. No T02/T03 failures are disguised as successful cancel tests.
