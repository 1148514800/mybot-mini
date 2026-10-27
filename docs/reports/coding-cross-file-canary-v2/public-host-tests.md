# Public and independent acceptance

Actual verified Seatbelt runs: buggy baseline Public FAIL (8 tests), Host FAIL (18 tests); Reference Public PASS 8/8 and Host PASS 18/18. The host is not importing candidate modules. Separate fresh read-only candidate copies execute each suite in the existing coding_judge.run_suite sandbox with timeout 10s and 8192-byte output bound, after sandbox sentinels pass.

Public: parser rows/id, quoted commas, category strip, Decimal type; simple totals, first-category order, negative totals, .10+.20.

Host: parser keys/order/id/input preservation; parser/report integration dependency; Unicode; duplicates; noncontiguous categories; zero; positive/negative cancellation; exact .10+.20-.05; malformed money; NaN/Infinity; lexical scale >2; quoted comma and escaped quote; header-only; case-sensitive categories; signed decimal/whitespace forms; wrong header/missing/extra fields/malformed quotes; blank lines; large exact amounts.

Integration spying accepts both module-qualified and ordinary directly imported aliases of parse_records. An alternate legitimate direct-import implementation is independently tested. The scorer compares behavior, never candidate bytes against Reference. Other exotic Python indirection and actively hostile interpreter/test tampering are outside this bounded nonadversarial canary.

Hidden test assertions and outputs are never sent back into the AgentLoop. Independently passing tests do not establish native receipt, authority, current revision or human approval: those dimensions have separate evidence.
